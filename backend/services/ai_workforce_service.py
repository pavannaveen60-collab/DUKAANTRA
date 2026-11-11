"""Persisted, owner-scoped orchestration for deterministic AI analyses."""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from agents.demand_agent import run_demand_agent
from agents.inventory_agent import run_inventory_agent
from agents.orchestrator import build_orchestration_report
from agents.sales_agent import run_sales_agent
from models.agent_task import AgentTask
from services.analytics_service import verify_shop_ownership


logger = logging.getLogger(__name__)

ORCHESTRATOR_NAME = "business_orchestrator"
WORKFLOW_TYPE = "full_analysis"
AGENT_RUNNERS = (
    ("inventory", "Inventory Intelligence", run_inventory_agent),
    ("sales", "Sales and Growth Intelligence", run_sales_agent),
    ("demand", "Demand Intelligence", run_demand_agent),
)


class AnalysisAlreadyRunning(Exception):
    """Raised when a shop already has an active workforce run."""


class AnalysisExecutionError(Exception):
    """Raised after a failed analysis has been persisted for the merchant."""


def _lock_key(shop_id: UUID) -> int:
    return int.from_bytes(shop_id.bytes[:8], byteorder="big", signed=True)


def _workflow_query(shop_id: UUID):
    return (
        select(AgentTask)
        .where(
            AgentTask.shop_id == shop_id,
            AgentTask.agent_name == ORCHESTRATOR_NAME,
            AgentTask.task_type == WORKFLOW_TYPE,
        )
        .order_by(AgentTask.created_at.desc())
    )


def _task_summary(task: AgentTask) -> dict[str, Any]:
    return {
        "task_id": str(task.id),
        "status": task.status,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "error": task.error_message,
        "report": task.result_data,
    }


def run_ai_workforce(
    db: Session,
    current_user: Any,
    shop_id: UUID,
) -> dict[str, Any]:
    verify_shop_ownership(db, current_user, shop_id)

    # A transaction-scoped PostgreSQL advisory lock serializes runs per shop.
    # The active-task check occurs while holding that lock, so concurrent API
    # requests cannot both start duplicate work.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _lock_key(shop_id)},
    )
    active_task = db.scalar(
        select(AgentTask.id)
        .where(
            AgentTask.shop_id == shop_id,
            AgentTask.agent_name == ORCHESTRATOR_NAME,
            AgentTask.task_type == WORKFLOW_TYPE,
            AgentTask.status.in_(("pending", "running")),
        )
        .limit(1)
    )
    if active_task is not None:
        db.rollback()
        raise AnalysisAlreadyRunning("An analysis is already running for this shop.")

    run_id = uuid4()
    workflow_task = AgentTask(
        id=run_id,
        shop_id=shop_id,
        agent_name=ORCHESTRATOR_NAME,
        task_type=WORKFLOW_TYPE,
        input_data={"run_id": str(run_id)},
        result_data=None,
        status="pending",
        started_at=None,
    )
    agent_tasks: dict[str, AgentTask] = {}
    for agent_type, label, _runner in AGENT_RUNNERS:
        agent_tasks[agent_type] = AgentTask(
            id=uuid4(),
            shop_id=shop_id,
            agent_name=agent_type,
            task_type=WORKFLOW_TYPE,
            input_data={"run_id": str(run_id), "label": label},
            result_data=None,
            status="pending",
            started_at=None,
        )
    db.add(workflow_task)
    db.add_all(list(agent_tasks.values()))
    db.commit()

    results: dict[str, dict[str, Any]] = {}
    agent_completed_at: dict[str, datetime] = {}
    started_at = datetime.now(timezone.utc)
    try:
        for task in (workflow_task, *agent_tasks.values()):
            task.status = "running"
            task.started_at = started_at
        db.commit()

        for agent_type, _label, runner in AGENT_RUNNERS:
            result = runner(db, current_user, shop_id)
            results[agent_type] = result
            task = agent_tasks[agent_type]
            task.result_data = result
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            agent_completed_at[agent_type] = task.completed_at
            db.commit()

        completed_at = datetime.now(timezone.utc)
        report = build_orchestration_report(
            results,
            str(run_id),
            started_at,
            completed_at,
            agent_completed_at,
        )
        workflow_task.result_data = report
        workflow_task.status = "completed"
        workflow_task.completed_at = completed_at
        db.commit()
        return report
    except Exception as error:
        db.rollback()
        failed_at = datetime.now(timezone.utc)
        for task in (workflow_task, *agent_tasks.values()):
            if task.status in ("pending", "running"):
                task.status = "failed"
                task.error_message = f"{type(error).__name__}: analysis failed."
                task.completed_at = failed_at
        failed_report = build_orchestration_report(
            results,
            str(run_id),
            started_at,
            failed_at,
            agent_completed_at,
        )
        failed_report["status"] = "failed"
        failed_report["action_plan"]["note"] = (
            "The analysis did not complete; findings from completed agents are "
            "partial and no business actions were taken."
        )
        workflow_task.result_data = failed_report
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not persist failed AI workforce run %s", run_id)
        logger.exception("AI workforce run %s failed", run_id)
        raise AnalysisExecutionError(
            "The AI workforce analysis failed. Review execution history and retry."
        ) from error


def get_ai_workforce_status(
    db: Session,
    current_user: Any,
    shop_id: UUID,
) -> dict[str, Any]:
    verify_shop_ownership(db, current_user, shop_id)
    tasks = list(db.scalars(_workflow_query(shop_id).limit(20)).all())
    latest = tasks[0] if tasks else None
    latest_run_id = (
        latest.input_data.get("run_id")
        if latest and isinstance(latest.input_data, dict)
        else None
    )
    agent_tasks = (
        list(
            db.scalars(
                select(AgentTask)
                .where(
                    AgentTask.shop_id == shop_id,
                    AgentTask.task_type == WORKFLOW_TYPE,
                    AgentTask.agent_name.in_(
                        tuple(agent_type for agent_type, _label, _runner in AGENT_RUNNERS)
                    ),
                )
                .order_by(AgentTask.created_at.desc())
                .limit(60)
            ).all()
        )
        if latest_run_id
        else []
    )
    latest_agent_tasks = {
        task.agent_name: task
        for task in agent_tasks
        if isinstance(task.input_data, dict)
        and task.input_data.get("run_id") == latest_run_id
    }
    agents = [
        {
            "agent_type": agent_type,
            "name": label,
            "status": (
                latest_agent_tasks[agent_type].status
                if agent_type in latest_agent_tasks
                else "not_run"
            ),
            "execution_completed_at": (
                latest_agent_tasks[agent_type].completed_at.isoformat()
                if agent_type in latest_agent_tasks
                and latest_agent_tasks[agent_type].completed_at
                else None
            ),
            "error": (
                latest_agent_tasks[agent_type].error_message
                if agent_type in latest_agent_tasks
                else None
            ),
        }
        for agent_type, label, _runner in AGENT_RUNNERS
    ]
    return {
        "shop_id": str(shop_id),
        "status": latest.status if latest else "not_run",
        "latest_run": _task_summary(latest) if latest else None,
        "agents": agents,
        "history": [_task_summary(task) for task in tasks],
    }
