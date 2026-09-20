"""The fun layer: What-if purchases, the daily briefing and the spending streak. Read-only and deterministic.

  * What-if     re-runs the cash-flow check with one hypothetical payment added (nothing is stored)
  * Streak      consecutive days (ending yesterday) where discretionary spend stayed at or under the user's usual
  * Briefing    a few short lines pulled from the cash-flow check, the streak and the savings status
  * Tone        chill | coach | roast only changes the wording. Every number comes from the same services.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg

from app.config import get_settings
from app.ledger import money
from app.services import queries
from app.services.cashflow_risk import DEFAULT_HORIZON_DAYS, check_upcoming_financial_risk, priority_for
from app.services.cycle_state import as_of, savings_progress_for
from app.services.savings import inr

ZERO = Decimal("0.00")
TONES = ("chill", "coach", "roast")
LEVEL_ORDER = {"SAFE": 0, "WATCH": 1, "AT_RISK": 2, "SHORTFALL": 3}
LEVEL_ICON = {"SAFE": "🟢", "WATCH": "🟡", "AT_RISK": "🟠", "SHORTFALL": "🔴"}
BADGES = [(30, "Iron Wallet"), (14, "Budget Ninja"), (7, "Week Warrior"), (3, "Getting Started")]
HISTORY_DAYS = 60
ALLOWANCE_DAYS = 30
MIN_HISTORY_DAYS = 7


def clean_tone(tone: Optional[str]) -> str:
    return tone if tone in TONES else "chill"


# ------------------------------------------------------------------ what-if

def simulate_purchase(
    conn: psycopg.Connection, user_id: str, account_id: str, amount: Decimal, label: str = "Purchase", days_from_now: int = 0,
) -> dict:
    """What happens to the cash-flow picture if the user spends `amount` on `label` in `days_from_now` days."""
    tz = ZoneInfo(get_settings().app_timezone)
    now = as_of(conn, user_id, account_id)
    horizon = max(DEFAULT_HORIZON_DAYS, days_from_now + 1)
    due = now + timedelta(days=days_from_now)
    local = due.astimezone(tz)
    label = (label or "Purchase").strip()[:60] or "Purchase"
    hypothetical = {
        "merchant": label, "category": None, "amount": money(amount), "due_at": due, "due_label": f"{local:%b} {local.day}",
        "days_remaining": days_from_now, "priority": priority_for(None), "frequency": "one-off",
    }
    before = check_upcoming_financial_risk(conn, user_id, account_id, horizon_days=horizon)
    after = check_upcoming_financial_risk(conn, user_id, account_id, horizon_days=horizon, extra_payments=[hypothetical])

    b, a = before["risk_level"], after["risk_level"]
    worse = LEVEL_ORDER[a] > LEVEL_ORDER[b]
    when = "today" if days_from_now <= 0 else f"in {days_from_now} day{'s' if days_from_now != 1 else ''}"
    if worse:
        verdict = f"Buying {label} for {inr(amount)} {when} would move you from {b} to {a}. {after['warning_message']}"
    elif a == "SAFE":
        verdict = (f"You can afford {label} for {inr(amount)} {when}. After it and your upcoming payments, "
                   f"your lowest balance would be {inr(after['lowest_balance'])}, still above your {inr(after['safety_buffer'])} buffer.")
    else:
        verdict = (f"{label} for {inr(amount)} {when} does not change your status ({a}), but your lowest balance would "
                   f"drop from {inr(before['lowest_balance'])} to {inr(after['lowest_balance'])}. {after['warning_message']}")
    return {
        "label": label, "amount": money(amount), "days_from_now": days_from_now,
        "risk_before": b, "risk_after": a, "risk_worsened": worse,
        "lowest_balance_before": before["lowest_balance"], "lowest_balance_after": after["lowest_balance"],
        "projected_balance_before": before["projected_balance"], "projected_balance_after": after["projected_balance"],
        "shortfall_after": after["shortfall_amount"],
        "savings_impact": after["savings_impact"], "budget_impact": after["budget_impact"],
        "verdict": verdict, "timeline": after["timeline"],
        "note": "Hypothetical only. Nothing was recorded, paid or changed.",
    }


# ------------------------------------------------------------------- streak

def _discretionary_by_day(conn: psycopg.Connection, user_id: str, account_id: str, since, tz_name: str) -> dict:
    rows = conn.execute(
        """
        select (("timestamp" at time zone %s)::date) as day, sum(amount) as total
        from transactions
        where user_id = %s and account_id = %s and transaction_type = 'EXPENSE' and not is_recurring
          and (("timestamp" at time zone %s)::date) >= %s
        group by 1
        """,
        (tz_name, user_id, account_id, tz_name, since),
    ).fetchall()
    return {r["day"]: r["total"] for r in rows}


def spending_streak(conn: psycopg.Connection, user_id: str, account_id: str) -> dict:
    """Days in a row (ending yesterday) where non-recurring spend was at or under the user's usual daily amount."""
    tz_name = get_settings().app_timezone
    tz = ZoneInfo(tz_name)
    today = as_of(conn, user_id, account_id).astimezone(tz).date()
    first_ts = conn.execute(
        'select min("timestamp") as ts from transactions where user_id = %s and account_id = %s', (user_id, account_id)
    ).fetchone()["ts"]
    first = first_ts.astimezone(tz).date() if first_ts else None
    if first is None or (today - first).days < MIN_HISTORY_DAYS:
        return {"available": False, "reason": "Not enough history yet (needs about a week of transactions).",
                "current_streak": 0, "best_streak": 0, "badge": None, "no_spend_days_30": 0, "daily_allowance": None}

    by_day = _discretionary_by_day(conn, user_id, account_id, today - timedelta(days=HISTORY_DAYS), tz_name)
    window = [today - timedelta(days=i) for i in range(1, ALLOWANCE_DAYS + 1)]
    allowance = (sum((by_day.get(d, ZERO) for d in window), ZERO) / ALLOWANCE_DAYS).quantize(Decimal("0.01"))

    def ok(d) -> bool:
        return by_day.get(d, ZERO) <= allowance

    current, d = 0, today - timedelta(days=1)
    while d >= first and ok(d) and current < HISTORY_DAYS:
        current += 1
        d -= timedelta(days=1)
    best = run = 0
    for i in range(HISTORY_DAYS, 0, -1):
        day = today - timedelta(days=i)
        run = run + 1 if (day >= first and ok(day)) else 0
        best = max(best, run)
    badge = next((name for n, name in BADGES if max(current, best) >= n), None)
    return {
        "available": True, "current_streak": current, "best_streak": best, "badge": badge,
        "daily_allowance": allowance, "no_spend_days_30": sum(1 for x in window if x >= first and by_day.get(x, ZERO) == 0),
        "explanation": f"A day counts when your non-recurring spending is at or under your usual {inr(allowance)}/day.",
    }


# ----------------------------------------------------------------- briefing

VOICE = {
    "chill": {
        "open": "Here's your money check-in.",
        "streak": "{n}-day streak of staying under your usual spend. Nice and steady.",
        "no_streak": "No streak running right now. Tomorrow's a fresh start.",
    },
    "coach": {
        "open": "Game plan for today.",
        "streak": "{n} days in a row under your usual spend. Keep the momentum going!",
        "no_streak": "Streak reset. Get one good day on the board today and rebuild it.",
    },
    "roast": {
        "open": "Ah, you're back. Let's see the damage.",
        "streak": "{n} days under your usual spend. Who are you and what did you do with the real you?",
        "no_streak": "Streak: zero. The delivery apps send their thanks.",
    },
}


def build_briefing(conn: psycopg.Connection, user_id: str, account_id: str, tone: Optional[str] = None) -> dict:
    tone = clean_tone(tone)
    v = VOICE[tone]
    items: list[dict] = []

    risk = check_upcoming_financial_risk(conn, user_id, account_id)
    level = risk["risk_level"]
    items.append({"kind": "cashflow", "level": level, "icon": LEVEL_ICON[level], "text": risk["warning_message"]})
    if risk["upcoming_payments"] and level == "SAFE":
        p = risk["upcoming_payments"][0]
        due = "today" if p["days_remaining"] <= 0 else f"in {p['days_remaining']} day{'s' if p['days_remaining'] != 1 else ''}"
        items.append({"kind": "next_payment", "level": "SAFE", "icon": "🔔", "text": f"Next up: {p['merchant']} {inr(p['amount'])} due {due}."})

    streak = spending_streak(conn, user_id, account_id)
    if streak["available"]:
        n = streak["current_streak"]
        text = v["streak"].format(n=n) if n >= 2 else v["no_streak"]
        if streak["badge"]:
            text += f" Badge: {streak['badge']}."
        items.append({"kind": "streak", "level": "SAFE" if n >= 2 else "WATCH", "icon": "🔥" if n >= 2 else "💤", "text": text})

    cycle = queries.active_cycle(conn, user_id, account_id)
    if cycle is not None:
        progress = savings_progress_for(conn, user_id, cycle)
        if progress.target is not None:
            items.append({"kind": "savings", "level": "WATCH" if progress.status == "AT_RISK" else "SAFE",
                          "icon": "🐷", "text": progress.message})

    return {"tone": tone, "greeting": v["open"], "risk_level": level, "streak": streak, "items": items,
            "as_of": as_of(conn, user_id, account_id)}
