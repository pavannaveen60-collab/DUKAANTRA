"""Controlled orchestration and prioritization for merchant intelligence."""

import re
from datetime import datetime, timezone
from typing import Any


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
AGENT_ORDER = ("inventory", "sales", "demand")


def _priority_for(finding: dict[str, Any]) -> str:
    evidence = finding.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    if finding.get("category") == "inventory":
        stock = evidence.get("current_stock")
        threshold = evidence.get("low_stock_threshold")
        if isinstance(stock, (int, float)) and isinstance(threshold, (int, float)):
            if stock == 0:
                return "critical"
            if stock <= threshold:
                return "high"
        days = evidence.get("estimated_days_of_stock")
        if isinstance(days, (int, float)):
            if days <= 3:
                return "high"
            if days <= 7:
                return "medium"
    requested = finding.get("priority")
    return requested if requested in PRIORITY_ORDER else "low"


def prioritize_findings(agent_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    seen_ids: set[str] = set()

    for agent_name in AGENT_ORDER:
        report = agent_results.get(agent_name)
        if not isinstance(report, dict):
            continue
        findings = report.get("findings")
        if not isinstance(findings, list):
            continue
        for raw in findings:
            if not isinstance(raw, dict):
                continue
            title = raw.get("title")
            recommendation = raw.get("recommendation")
            evidence = raw.get("evidence")
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(recommendation, str) or not recommendation.strip():
                continue
            if not isinstance(evidence, dict):
                continue
            category = str(raw.get("category") or agent_name)
            product_id = str(raw.get("product_id") or "")
            normalized_title = re.sub(r"\s+", " ", title.strip().casefold())
            key = (product_id, "" if product_id else category, normalized_title)
            finding_id = str(raw.get("id") or "")
            if key in seen or (finding_id and finding_id in seen_ids):
                continue
            seen.add(key)
            if finding_id:
                seen_ids.add(finding_id)
            finding = {
                "id": finding_id or f"{agent_name}:{len(collected) + 1}",
                "agent": agent_name,
                "category": category,
                "priority": _priority_for(raw),
                "title": title.strip(),
                "explanation": str(raw.get("explanation") or ""),
                "evidence": evidence,
                "recommendation": recommendation.strip(),
                "action_status": "pending_approval",
                "action_completed": False,
            }
            if product_id:
                finding["product_id"] = product_id
            if isinstance(raw.get("product_name"), str):
                finding["product_name"] = raw["product_name"]
            collected.append(finding)

    return sorted(
        collected,
        key=lambda item: (
            PRIORITY_ORDER[item["priority"]],
            item["agent"],
            item["title"].casefold(),
        ),
    )


def build_orchestration_report(
    agent_results: dict[str, dict[str, Any]],
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    agent_completed_at: dict[str, datetime] | None = None,
) -> dict[str, Any]:
    items = prioritize_findings(agent_results)
    agent_completed_at = agent_completed_at or {}
    agent_labels = {
        "inventory": "Inventory Intelligence",
        "sales": "Sales and Growth Intelligence",
        "demand": "Demand Intelligence",
    }
    return {
        "run_id": run_id,
        "status": "completed",
        "generated_at": completed_at.astimezone(timezone.utc).isoformat(),
        "started_at": started_at.astimezone(timezone.utc).isoformat(),
        "completed_at": completed_at.astimezone(timezone.utc).isoformat(),
        "agents": [
            {
                "name": agent_labels[name],
                "agent_type": name,
                "status": (
                    "completed"
                    if agent_results.get(name, {}).get("status") == "completed"
                    else "failed"
                ),
                "execution_completed_at": (
                    agent_completed_at.get(name, completed_at)
                    .astimezone(timezone.utc)
                    .isoformat()
                ),
            }
            for name in AGENT_ORDER
        ],
        "agent_results": agent_results,
        "action_plan": {
            "total": len(items),
            "by_priority": {
                priority: sum(item["priority"] == priority for item in items)
                for priority in PRIORITY_ORDER
            },
            "items": items,
            "priority_rules": [
                "Critical: inventory is at zero.",
                "High: positive inventory is at or below its configured threshold, or estimated stock coverage is 3 days or less.",
                "Medium: estimated stock coverage is 4-7 days, a confirmed-revenue decrease is at least 25%, demand has increased at least 50%, or a repeated co-purchase pattern is found.",
                "Low: other evidence-backed review suggestions.",
            ],
            "note": (
                "Recommendations are suggestions only. No inventory, pricing, "
                "orders, payments, or customer messages were changed."
            ),
        },
    }