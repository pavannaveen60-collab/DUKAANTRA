import json
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from agents.demand_agent import build_demand_report
from agents.growth_agent import build_growth_findings
from agents.inventory_agent import build_inventory_report, run_inventory_agent
from agents.orchestrator import build_orchestration_report, prioritize_findings
from agents.sales_agent import build_sales_report, run_sales_agent
from api.routes import ai_workforce as workforce_routes
from models.shop import Shop
from services import ai_workforce_service
from services.analytics_service import verify_shop_ownership


class InventoryIntelligenceTests(unittest.TestCase):
    def test_threshold_reorder_and_slow_moving_findings_use_sales_evidence(self):
        today = date(2026, 11, 11)
        critical_product = SimpleNamespace(id=uuid.uuid4(), name="Milk")
        slow_product = SimpleNamespace(id=uuid.uuid4(), name="Tea")
        products = [
            (
                critical_product,
                SimpleNamespace(quantity=0, low_stock_threshold=5),
            ),
            (
                slow_product,
                SimpleNamespace(quantity=40, low_stock_threshold=5),
            ),
            (SimpleNamespace(id=uuid.uuid4(), name="Bread"), None),
        ]
        sales = [
            SimpleNamespace(
                product_id=critical_product.id,
                units_sold=28,
                sale_days=10,
                history_sale_days=10,
                first_sale=today - timedelta(days=20),
            ),
            SimpleNamespace(
                product_id=slow_product.id,
                units_sold=0,
                sale_days=0,
                history_sale_days=8,
                first_sale=today - timedelta(days=60),
            ),
        ]

        report = build_inventory_report(products, sales, today)
        by_name = {item["product_name"]: item for item in report["products"]}
        findings = {item["title"]: item for item in report["findings"]}

        self.assertEqual(by_name["Milk"]["suggested_reorder_quantity"], 24)
        self.assertEqual(findings["Out of stock: Milk"]["priority"], "critical")
        self.assertEqual(by_name["Tea"]["history_status"], "insufficient_data")
        self.assertIn("Review slow-moving stock: Tea", findings)
        self.assertEqual(by_name["Bread"]["status"], "missing_inventory")
        self.assertIsNone(by_name["Bread"]["current_stock"])

    def test_inventory_query_scopes_shop_and_counts_only_confirmed_orders(self):
        user = SimpleNamespace(id=uuid.uuid4())
        shop_id = uuid.uuid4()
        db = Mock()
        db.scalar.return_value = SimpleNamespace(id=shop_id)
        product = SimpleNamespace(
            id=uuid.uuid4(),
            name="Milk",
            is_active=True,
        )
        inventory = SimpleNamespace(quantity=0, low_stock_threshold=5)
        db.execute.side_effect = [
            SimpleNamespace(all=Mock(return_value=[(product, inventory)])),
            SimpleNamespace(all=Mock(return_value=[])),
        ]

        with patch(
            "agents.inventory_agent.verify_shop_ownership",
            return_value=SimpleNamespace(id=shop_id),
        ):
            run_inventory_agent(db, user, shop_id)

        product_sql = str(db.execute.call_args_list[0].args[0].compile(dialect=postgresql.dialect()))
        sales_statement = db.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect())
        self.assertIn("products.shop_id", product_sql)
        self.assertIn("inventory.shop_id", product_sql)
        self.assertIn("orders.status", str(sales_statement))
        self.assertIn("confirmed", sales_statement.params.values())
        self.assertIn(shop_id, sales_statement.params.values())


class SalesAndGrowthIntelligenceTests(unittest.TestCase):
    def test_aov_revenue_and_growth_comparison_use_confirmed_order_summary(self):
        products = [
            (
                SimpleNamespace(id=uuid.uuid4(), name="Coffee"),
                SimpleNamespace(quantity=7),
            ),
            (
                SimpleNamespace(id=uuid.uuid4(), name="Cups"),
                SimpleNamespace(quantity=4),
            ),
        ]
        summary = SimpleNamespace(order_count=2, revenue=Decimal("200.00"))
        period = SimpleNamespace(
            current_orders=2,
            previous_orders=3,
            current_revenue=Decimal("200.00"),
            previous_revenue=Decimal("300.00"),
        )
        report = build_sales_report(summary, [], products, [], period)

        self.assertEqual(report["metrics"]["confirmed_orders"], 2)
        self.assertEqual(report["metrics"]["confirmed_revenue"], 200.0)
        self.assertEqual(report["metrics"]["average_order_value"], 100.0)
        self.assertEqual(report["growth_comparison"]["revenue_change_percent"], -33.3)
        self.assertEqual(report["findings"][0]["priority"], "medium")
        self.assertEqual(len(report["slow_movers"]), 2)

    def test_sales_agent_queries_filter_shop_and_confirmed_orders(self):
        shop_id = uuid.uuid4()
        db = Mock()
        order_summary = SimpleNamespace(order_count=1, revenue=Decimal("35.00"))
        comparison = SimpleNamespace(
            current_orders=1,
            current_revenue=Decimal("35.00"),
            previous_orders=0,
            previous_revenue=Decimal("0"),
        )
        results = [
            Mock(one=Mock(return_value=order_summary)),
            Mock(one=Mock(return_value=comparison)),
            Mock(all=Mock(return_value=[])),
            Mock(all=Mock(return_value=[])),
            Mock(all=Mock(return_value=[])),
        ]
        db.execute.side_effect = results

        with patch("agents.sales_agent.verify_shop_ownership"):
            report = run_sales_agent(db, SimpleNamespace(id=uuid.uuid4()), shop_id)

        self.assertEqual(report["metrics"]["confirmed_orders"], 1)
        for index in (0, 1, 2, 4):
            statement = db.execute.call_args_list[index].args[0]
            compiled = statement.compile(dialect=postgresql.dialect())
            self.assertIn("orders.status", str(compiled))
            self.assertIn("confirmed", compiled.params.values())
            self.assertIn(shop_id, compiled.params.values())

    def test_growth_does_not_invent_percent_when_previous_revenue_is_zero(self):
        comparison = SimpleNamespace(
            current_orders=1,
            previous_orders=1,
            current_revenue=Decimal("50"),
            previous_revenue=Decimal("0"),
        )
        result = build_growth_findings(comparison)
        self.assertEqual(result["status"], "available")
        self.assertIsNone(result["revenue_change_percent"])
        self.assertIsNotNone(result["finding"])


class DemandIntelligenceTests(unittest.TestCase):
    def test_sufficient_history_has_experimental_seven_day_estimate(self):
        today = date(2026, 11, 11)
        product = SimpleNamespace(id=uuid.uuid4(), name="Rice")
        rows = [
            SimpleNamespace(
                product_id=product.id,
                sale_date=today - timedelta(days=offset),
                units_sold=2,
            )
            for offset in (2, 4, 6, 9, 12, 15, 18)
        ]

        report = build_demand_report([product], rows, today)
        analysis = report["products"][0]

        self.assertEqual(report["forecast_status"], "available")
        self.assertEqual(analysis["status"], "forecast_available")
        self.assertEqual(analysis["estimated_units_next_7_days"], 5.2)
        self.assertIn("Experimental baseline", analysis["limitations"])
        self.assertEqual(report["findings"][0]["priority"], "medium")

    def test_insufficient_or_empty_history_withholds_forecast(self):
        product = SimpleNamespace(id=uuid.uuid4(), name="Spices")
        report = build_demand_report([product], [], date(2026, 11, 11))

        self.assertEqual(report["forecast_status"], "insufficient_data")
        self.assertEqual(report["products"][0]["status"], "insufficient_data")
        self.assertIsNone(report["products"][0]["estimated_units_next_7_days"])

    def test_demand_query_is_shop_scoped_and_confirmed_only(self):
        shop_id = uuid.uuid4()
        product = SimpleNamespace(id=uuid.uuid4(), name="Rice")
        db = Mock()
        db.scalar.return_value = SimpleNamespace(id=shop_id)
        db.scalars.return_value.all.return_value = [product]
        rows_result = Mock(all=Mock(return_value=[]))
        db.execute.return_value = rows_result

        with patch(
            "agents.demand_agent.verify_shop_ownership",
            return_value=SimpleNamespace(id=shop_id),
        ):
            from agents.demand_agent import run_demand_agent
            report = run_demand_agent(db, SimpleNamespace(id=uuid.uuid4()), shop_id)

        self.assertEqual(report["forecast_status"], "insufficient_data")
        compiled = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertIn("orders.status", str(compiled))
        self.assertIn("products.shop_id", str(compiled))
        self.assertIn("confirmed", compiled.params.values())
        self.assertIn(shop_id, compiled.params.values())


class OrchestrationTests(unittest.TestCase):
    def test_findings_are_deduplicated_and_prioritized_with_explicit_rules(self):
        duplicate = {
            "id": "same",
            "agent": "inventory",
            "category": "inventory",
            "priority": "low",
            "product_id": "prod-1",
            "title": "Check milk stock",
            "explanation": "Threshold exceeded.",
            "evidence": {"current_stock": 0, "low_stock_threshold": 5},
            "recommendation": "Review reorder.",
        }
        medium = {
            "id": "medium",
            "agent": "demand",
            "category": "demand",
            "priority": "medium",
            "title": "Review trend",
            "explanation": "Recent demand increased.",
            "evidence": {"change_percent": 60},
            "recommendation": "Review future demand.",
        }
        results = {
            "inventory": {"status": "completed", "findings": [duplicate]},
            "sales": {
                "status": "completed",
                "findings": [{**duplicate, "id": "same-other-category", "category": "growth"}, medium],
            },
            "demand": {"status": "completed", "findings": []},
        }

        findings = prioritize_findings(results)

        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0]["priority"], "critical")
        self.assertEqual(findings[0]["action_status"], "pending_approval")
        self.assertFalse(findings[0]["action_completed"])
        self.assertEqual(findings[1]["priority"], "medium")

    def test_orchestrator_report_tracks_agents_and_action_plan(self):
        results = {
            name: {"agent": name, "status": "completed", "findings": []}
            for name in ("inventory", "sales", "demand")
        }
        now = datetime.now(timezone.utc)
        report = build_orchestration_report(results, "run-id", now, now)

        self.assertEqual(report["status"], "completed")
        self.assertEqual(len(report["agents"]), 3)
        self.assertEqual(report["action_plan"]["total"], 0)
        json.dumps(report)

    def test_workflow_persists_agent_results_and_timestamps(self):
        shop_id = uuid.uuid4()
        db = Mock()
        db.scalar.return_value = None
        agent_results = {
            name: {"agent": name, "status": "completed", "findings": []}
            for name in ("inventory", "sales", "demand")
        }
        runners = tuple(
            (name, name.title(), lambda *_args, result=agent_results[name]: result)
            for name in ("inventory", "sales", "demand")
        )
        persisted_statuses = []

        def capture_persisted_statuses():
            workflow = db.add.call_args.args[0]
            subtasks = db.add_all.call_args.args[0]
            persisted_statuses.append(
                [workflow.status, *(task.status for task in subtasks)]
            )

        db.commit.side_effect = capture_persisted_statuses
        with (
            patch.object(ai_workforce_service, "verify_shop_ownership"),
            patch.object(ai_workforce_service, "AGENT_RUNNERS", runners),
        ):
            report = ai_workforce_service.run_ai_workforce(
                db,
                SimpleNamespace(id=uuid.uuid4()),
                shop_id,
            )

        self.assertEqual(report["status"], "completed")
        self.assertEqual(db.commit.call_count, 6)
        self.assertEqual(persisted_statuses[0], ["pending"] * 4)
        self.assertEqual(persisted_statuses[1], ["running"] * 4)
        self.assertIn("pg_advisory_xact_lock", str(db.execute.call_args.args[0]))
        workflow = db.add.call_args.args[0]
        self.assertEqual(workflow.status, "completed")
        self.assertIsNotNone(workflow.started_at)
        self.assertIsNotNone(workflow.completed_at)
        for task in db.add_all.call_args.args[0]:
            self.assertEqual(task.status, "completed")
            self.assertIsNotNone(task.result_data)

    def test_duplicate_run_is_rejected_while_active(self):
        db = Mock()
        db.scalar.return_value = uuid.uuid4()
        with patch.object(ai_workforce_service, "verify_shop_ownership"):
            with self.assertRaises(ai_workforce_service.AnalysisAlreadyRunning):
                ai_workforce_service.run_ai_workforce(
                    db,
                    SimpleNamespace(id=uuid.uuid4()),
                    uuid.uuid4(),
                )
        db.rollback.assert_called_once()
        db.add.assert_not_called()

    def test_agent_failure_is_persisted_and_returned_as_safe_error(self):
        db = Mock()
        db.scalar.return_value = None

        def fail(*_args):
            raise RuntimeError("private database detail")

        runners = (("inventory", "Inventory", fail),)
        with (
            patch.object(ai_workforce_service, "verify_shop_ownership"),
            patch.object(ai_workforce_service, "AGENT_RUNNERS", runners),
        ):
            with self.assertRaises(ai_workforce_service.AnalysisExecutionError) as raised:
                ai_workforce_service.run_ai_workforce(
                    db,
                    SimpleNamespace(id=uuid.uuid4()),
                    uuid.uuid4(),
                )

        self.assertNotIn("private database detail", str(raised.exception))
        workflow = db.add.call_args.args[0]
        agent = db.add_all.call_args.args[0][0]
        self.assertEqual(workflow.status, "failed")
        self.assertEqual(agent.status, "failed")
        self.assertNotIn("private database detail", agent.error_message)

    def test_shop_ownership_filter_prevents_cross_merchant_access(self):
        db = Mock()
        db.scalar.return_value = None
        user = SimpleNamespace(id=uuid.uuid4())

        with self.assertRaises(ValueError):
            verify_shop_ownership(db, user, uuid.uuid4())

        statement = db.scalar.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertIn("shops.owner_id", str(compiled))
        self.assertIn(user.id, compiled.params.values())

    def test_unauthorized_workforce_status_returns_not_found(self):
        with patch.object(
            workforce_routes,
            "get_ai_workforce_status",
            side_effect=ValueError("Shop not found or access denied."),
        ):
            with self.assertRaises(HTTPException) as raised:
                workforce_routes.read_ai_workforce(
                    uuid.uuid4(),
                    Mock(),
                    SimpleNamespace(id=uuid.uuid4()),
                )
        self.assertEqual(raised.exception.status_code, 404)

    def test_status_history_query_is_limited_to_requested_shop(self):
        shop_id = uuid.uuid4()
        db = Mock()
        db.scalars.return_value.all.return_value = []
        with patch.object(ai_workforce_service, "verify_shop_ownership"):
            status_report = ai_workforce_service.get_ai_workforce_status(
                db,
                SimpleNamespace(id=uuid.uuid4()),
                shop_id,
            )
        self.assertEqual(status_report["status"], "not_run")
        self.assertEqual(len(status_report["agents"]), 3)
        compiled = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertIn("agent_tasks.shop_id", str(compiled))
        self.assertIn(shop_id, compiled.params.values())


if __name__ == "__main__":
    unittest.main()
