"""Savings target & risk engine. Deterministic, grounded in the ledger.

Definitions (all for one financial cycle):

  income               = SALARY + OTHER_INCOME + INTEREST received in the cycle
  net_spend            = EXPENSE - REFUND
  planned_spend_limit  = income - target          (the most you can spend and still hit the target)
  remaining_capacity   = planned_spend_limit - net_spend
  estimated_savings    = income - net_spend        (what would be left of this cycle's income right now)
  required_more        = max(0, target - estimated_savings)   (shortfall already locked in)

Money received from other people (TRANSFER_IN) is reported as "other inflows"; it is not part
of income and is not used to make the target look better than it is.

Projection (only used when there is history): assume the rest of the cycle looks like the
user's own recent cycles.

  projected_spend = net_spend + avg_recent_net_spend * (1 - elapsed/expected_cycle_days)

Status:
  NO_TARGET          the user has not set one (FinPilot never invents a target)
  INSUFFICIENT_DATA  no income recorded in this cycle yet
  AT_RISK            net_spend already exceeds the limit, or projected_spend does
  ON_TRACK           otherwise
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Sequence

from app.ledger import money

ZERO = Decimal("0.00")


@dataclass
class SavingsProgress:
    status: str
    reason: Optional[str]
    target: Optional[Decimal]
    income: Decimal
    other_inflows: Decimal
    expenses: Decimal
    refunds: Decimal
    net_spend: Decimal
    planned_spend_limit: Optional[Decimal]
    remaining_spend_capacity: Optional[Decimal]
    estimated_savings: Decimal
    required_more_savings: Optional[Decimal]
    projected_spend: Decimal
    projected_savings: Decimal
    projection_basis: str  # "recent_cycles" | "current_spend_only"
    message: str

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()}


def inr(value: Decimal) -> str:
    """Indian digit grouping, e.g. 135840 -> Rs 1,35,840 (no decimals unless needed)."""
    value = money(value)
    negative = value < 0
    value = abs(value)
    whole, frac = divmod(value, 1)
    digits = str(int(whole))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        digits = ",".join(parts + [tail])
    text = f"₹{digits}"
    if frac:
        text += f".{int(frac * 100):02d}"
    return f"-{text}" if negative else text


def inr0(value: Decimal) -> str:
    """Whole-rupee display for averages and projections (estimates read better without paise)."""
    return inr(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compute_savings_progress(
    *,
    income: Decimal,
    other_inflows: Decimal,
    expenses: Decimal,
    refunds: Decimal,
    target: Optional[Decimal],
    elapsed_days: float,
    recent_net_spends: Sequence[Decimal],
    recent_cycle_days: Sequence[float],
) -> SavingsProgress:
    income, other_inflows, expenses, refunds = money(income), money(other_inflows), money(expenses), money(refunds)
    net_spend = expenses - refunds
    estimated = income - net_spend

    if recent_net_spends:
        avg_spend = sum(recent_net_spends, ZERO) / len(recent_net_spends)
        expected_days = (sum(recent_cycle_days) / len(recent_cycle_days)) if recent_cycle_days else 30.0
        remaining_fraction = max(0.0, 1.0 - (elapsed_days / expected_days if expected_days else 1.0))
        projected_spend = net_spend + money(avg_spend * Decimal(str(remaining_fraction)))
        basis = "recent_cycles"
    else:
        projected_spend = net_spend
        basis = "current_spend_only"
    projected_savings = income - projected_spend

    base = dict(
        income=income, other_inflows=other_inflows, expenses=expenses, refunds=refunds, net_spend=net_spend,
        estimated_savings=estimated, projected_spend=projected_spend, projected_savings=projected_savings,
        projection_basis=basis,
    )

    if target is None:
        return SavingsProgress(
            status="NO_TARGET", reason=None, target=None, planned_spend_limit=None,
            remaining_spend_capacity=None, required_more_savings=None,
            message="You have not set a savings target for this cycle yet.", **base,
        )

    target = money(target)
    if income <= 0:
        return SavingsProgress(
            status="INSUFFICIENT_DATA", reason=None, target=target, planned_spend_limit=None,
            remaining_spend_capacity=None, required_more_savings=None,
            message="No income has been recorded in this cycle yet, so progress towards the target cannot be calculated.",
            **base,
        )

    limit = income - target
    remaining = limit - net_spend
    required_more = max(ZERO, target - estimated)

    if net_spend > limit:
        status, reason = "AT_RISK", "limit_exceeded"
        message = (
            f"You have spent {inr(net_spend)} from your {inr(income)} cycle income. Based on your current cycle, "
            f"reaching the {inr(target)} savings target is no longer possible from this cycle's income alone "
            f"(you would need {inr(required_more)} more in income or refunds)."
        )
    elif projected_spend > limit and basis == "recent_cycles":
        status, reason = "AT_RISK", "projected_shortfall"
        message = (
            f"You have spent {inr(net_spend)} so far. If the rest of this cycle looks like your recent cycles, "
            f"total spending would reach about {inr0(projected_spend)}, above the {inr(limit)} you can spend and still "
            f"save {inr(target)}."
        )
    else:
        status, reason = "ON_TRACK", None
        message = (
            f"You have spent {inr(net_spend)} of the {inr(limit)} you can spend this cycle and still save "
            f"{inr(target)}. {inr(remaining)} of spending capacity remains."
        )

    return SavingsProgress(
        status=status, reason=reason, target=target, planned_spend_limit=limit,
        remaining_spend_capacity=remaining, required_more_savings=required_more, message=message, **base,
    )


def elapsed_days(start: datetime, now: datetime) -> float:
    return max(0.0, (now - start).total_seconds() / 86400.0)
