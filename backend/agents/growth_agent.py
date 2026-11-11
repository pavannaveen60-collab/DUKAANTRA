"""Confirmed-revenue comparison used by Sales and Growth Intelligence."""

import math
from typing import Any


def _safe_float(value: Any) -> float:
    try:
        result = float(value or 0)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def build_growth_findings(period_comparison: Any) -> dict[str, Any]:
    current_revenue = round(_safe_float(period_comparison.current_revenue), 2)
    previous_revenue = round(_safe_float(period_comparison.previous_revenue), 2)
    current_orders = _safe_int(period_comparison.current_orders)
    previous_orders = _safe_int(period_comparison.previous_orders)

    if previous_orders == 0:
        return {
            "status": "insufficient_comparison",
            "current_period_days": 28,
            "previous_period_days": 28,
            "current_revenue": current_revenue,
            "previous_revenue": previous_revenue,
            "revenue_change_percent": None,
            "finding": None,
        }

    change_percent = (
        round((current_revenue - previous_revenue) / previous_revenue * 100, 1)
        if previous_revenue > 0
        else None
    )
    direction = (
        "increased" if current_revenue > previous_revenue
        else "decreased" if current_revenue < previous_revenue
        else "was unchanged"
    )
    finding = {
        "id": "growth:confirmed-revenue-comparison",
        "agent": "sales",
        "category": "growth",
        "priority": (
            "medium"
            if change_percent is not None and change_percent <= -25
            else "low"
        ),
        "title": f"Confirmed revenue {direction} between 28-day periods",
        "explanation": (
            f"Recorded confirmed revenue was ₹{previous_revenue:.2f} in the previous "
            f"period and ₹{current_revenue:.2f} in the latest period."
        ),
        "evidence": {
            "current_period_days": 28,
            "previous_period_days": 28,
            "current_confirmed_orders": current_orders,
            "previous_confirmed_orders": previous_orders,
            "current_confirmed_revenue": current_revenue,
            "previous_confirmed_revenue": previous_revenue,
            "revenue_change_percent": change_percent,
        },
        "recommendation": (
            "Review changes in product availability and customer demand."
            if change_percent is not None and change_percent <= -25
            else "Use the comparison as context; a revenue change does not establish its cause."
        ),
        "action_status": "pending_approval",
    }
    return {
        "status": "available",
        "current_period_days": 28,
        "previous_period_days": 28,
        "current_revenue": current_revenue,
        "previous_revenue": previous_revenue,
        "revenue_change_percent": change_percent,
        "finding": finding,
    }