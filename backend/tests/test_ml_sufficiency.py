import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy.dialects import postgresql

from services import ml_integration_service


def _result(rows):
    return SimpleNamespace(all=lambda: rows)


def _sales_row(sale_date, revenue=100, units=2, orders=1):
    return SimpleNamespace(
        sale_date=sale_date,
        revenue=Decimal(str(revenue)),
        units=units,
        orders=orders,
    )


class MLSufficiencyTests(unittest.TestCase):
    def setUp(self):
        self.user_id = uuid.uuid4()
        self.shop_id = uuid.uuid4()
        self.product_id = uuid.uuid4()
        self.user = SimpleNamespace(id=self.user_id)
        self.shop = SimpleNamespace(
            id=self.shop_id,
            owner_id=self.user_id,
            created_at=datetime.now(timezone.utc) - timedelta(days=365),
        )

    def make_sales_db(self, rows):
        db = Mock()
        db.scalar.return_value = self.shop
        db.execute.return_value = _result(rows)
        return db

    def make_product_db(self, history_rows):
        product = SimpleNamespace(
            id=self.product_id,
            name="Sample product",
            created_at=datetime.now(timezone.utc) - timedelta(days=365),
        )
        inventory = SimpleNamespace(quantity=8, low_stock_threshold=2)
        db = Mock()
        db.scalar.return_value = self.shop
        db.execute.side_effect = [
            _result([(product, inventory)]),
            _result(history_rows),
        ]
        return db

    @staticmethod
    def observed_sale_dates(count, start_offset=1):
        today = date.today()
        return [
            today - timedelta(days=offset)
            for offset in range(start_offset, start_offset + count)
        ]

    def statement_sql(self, db, execute_index=-1):
        statement = db.execute.call_args_list[execute_index].args[0]
        return str(statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ))

    def test_old_shop_without_confirmed_sales_has_no_zero_forecast(self):
        db = self.make_sales_db([])
        report = ml_integration_service.get_sales_forecast(
            db, self.user, self.shop_id
        )

        self.assertEqual(report["status"], "insufficient_data")
        self.assertIsNone(report["forecast"])
        self.assertEqual(report["confirmed_sales_observations"], 0)
        self.assertIn(f"'{self.shop_id}'", self.statement_sql(db))
        self.assertIn("orders.status = 'confirmed'", self.statement_sql(db))

    def test_sales_forecast_requires_fourteen_observed_confirmed_sale_days(self):
        rows = [
            _sales_row(sale_date, revenue=index * 10)
            for index, sale_date in enumerate(
                self.observed_sale_dates(13), start=1
            )
        ]
        report = ml_integration_service.get_sales_forecast(
            self.make_sales_db(rows), self.user, self.shop_id
        )

        self.assertEqual(report["status"], "insufficient_data")
        self.assertIsNone(report["forecast"])
        self.assertEqual(report["confirmed_sales_observations"], 13)

    def test_sales_forecast_uses_only_observed_dates_when_history_is_sufficient(self):
        rows = [
            _sales_row(sale_date, revenue=index * 10)
            for index, sale_date in enumerate(
                self.observed_sale_dates(14), start=1
            )
        ]
        report = ml_integration_service.get_sales_forecast(
            self.make_sales_db(rows), self.user, self.shop_id
        )

        self.assertEqual(report["status"], "experimental_baseline")
        self.assertEqual(report["confirmed_sales_observations"], 14)
        self.assertEqual(report["predicted_revenue"], 75)
        self.assertIn("no missing dates are treated as zero", report["forecast_method"])

    def test_old_product_without_confirmed_sales_has_no_zero_demand_estimate(self):
        db = self.make_product_db([])
        report = ml_integration_service.get_demand_and_stockout_predictions(
            db, self.user, self.shop_id
        )
        product = report["predictions"][0]

        self.assertEqual(product["status"], "insufficient_data")
        self.assertIsNone(product["estimated_7_day_demand"])
        self.assertEqual(product["confirmed_sales_observations"], 0)
        history_sql = self.statement_sql(db)
        self.assertIn(f"'{self.shop_id}'", history_sql)
        self.assertIn("orders.status = 'confirmed'", history_sql)
        self.assertIn(f"'{self.product_id}'", history_sql)

    def test_product_demand_requires_fourteen_observed_confirmed_sale_days(self):
        history = [
            SimpleNamespace(sale_date=sale_date, units_sold=2)
            for sale_date in self.observed_sale_dates(13)
        ]
        report = ml_integration_service.get_demand_and_stockout_predictions(
            self.make_product_db(history), self.user, self.shop_id
        )
        product = report["predictions"][0]

        self.assertEqual(product["status"], "insufficient_data")
        self.assertIsNone(product["estimated_7_day_demand"])
        self.assertEqual(product["confirmed_sales_observations"], 13)

    def test_product_demand_baseline_requires_confirmed_history_and_is_deterministic(self):
        history = [
            SimpleNamespace(sale_date=sale_date, units_sold=2)
            for sale_date in self.observed_sale_dates(14)
        ]
        report = ml_integration_service.get_demand_and_stockout_predictions(
            self.make_product_db(history), self.user, self.shop_id
        )
        product = report["predictions"][0]

        self.assertEqual(product["status"], "experimental_baseline")
        self.assertEqual(product["estimated_7_day_demand"], 14)
        self.assertEqual(product["stockout_risk"]["status"], "deterministic_baseline")
        self.assertIsNone(product["stockout_risk"]["stockout_probability"])

    def test_unconfirmed_only_sales_are_excluded_by_query_filter(self):
        db = self.make_sales_db([])
        report = ml_integration_service.get_sales_forecast(
            db, self.user, self.shop_id
        )

        self.assertEqual(report["status"], "insufficient_data")
        sql = self.statement_sql(db)
        self.assertIn("orders.status = 'confirmed'", sql)
        self.assertNotIn("orders.status != 'confirmed'", sql)

    def test_other_shop_rows_are_excluded_by_shop_scoped_query(self):
        db = self.make_sales_db([])
        ml_integration_service.get_sales_forecast(db, self.user, self.shop_id)
        sql = self.statement_sql(db)

        self.assertIn("orders.shop_id =", sql)
        self.assertIn(f"'{self.shop_id}'", sql)

    def test_anomaly_requires_observed_history_and_yesterday_sale(self):
        today = date.today()
        rows = [
            _sales_row(sale_date, revenue=100)
            for sale_date in self.observed_sale_dates(13, start_offset=2)
        ]
        rows.append(_sales_row(today - timedelta(days=1), revenue=100))
        db = self.make_sales_db(rows)

        report = ml_integration_service.get_sales_anomaly_report(
            db, self.user, self.shop_id
        )

        self.assertEqual(report["status"], "insufficient_data")
        self.assertIsNone(report["anomaly"])
        self.assertEqual(report["confirmed_sales_observations"], 13)
        sql = self.statement_sql(db)
        self.assertIn("orders.status = 'confirmed'", sql)
        self.assertIn(f"'{self.shop_id}'", sql)


if __name__ == "__main__":
    unittest.main()
