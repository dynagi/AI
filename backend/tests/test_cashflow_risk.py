"""Cash-flow warning: the pure engine (exact examples from the spec) and the demo scenario end to end."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.services.cashflow_risk import assess, check_upcoming_financial_risk
from app.services.demo_service import setup_cashflow_scenario
from tests.conftest import DEMO_ACCOUNT, DEMO_USER

D = Decimal
TZ = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=TZ)


def pay(merchant, amount, day, category="Subscriptions"):
    due = datetime(2026, 9, day, 10, 0, tzinfo=TZ)
    return {"merchant": merchant, "category": category, "amount": D(amount), "due_at": due, "due_label": f"Sep {day}",
            "days_remaining": (due.date() - NOW.date()).days, "priority": "low", "frequency": "monthly"}


def salary(day, amount="50000"):
    return {"label": "Salary", "amount": D(amount), "date": datetime(2026, 9, day, 9, 0, tzinfo=TZ), "date_label": f"Sep {day}", "days_remaining": day - 10}


def run(balance, payments, incomes=(), savings=None, spending=None, buffer="5000", cycle_end=None):
    return assess(now=NOW, balance=D(balance), payments=payments, incomes=list(incomes), buffer=D(buffer),
                  savings=savings, spending=spending, cycle_end=cycle_end, tz=TZ)


def test_core_example_is_a_shortfall():
    r = run("1000", [pay("Netflix", "2000", 15)])
    assert r["risk_level"] == "SHORTFALL"
    assert r["shortfall_amount"] == D("1000") and r["projected_balance"] == D("-1000")
    assert "₹2,000" in r["warning_message"] and "Sep 15" in r["warning_message"] and "₹1,000" in r["warning_message"]
    assert "No income is expected" in r["warning_message"]
    assert [t["kind"] for t in r["timeline"]] == ["start", "payment"]


def test_expected_salary_before_the_due_date_removes_the_shortfall():
    r = run("1000", [pay("Netflix", "2000", 15)], [salary(12)], buffer="0")
    assert r["risk_level"] == "SAFE" and r["covered_by_income"]
    assert r["projected_balance"] == D("49000")
    assert [t["kind"] for t in r["timeline"]] == ["start", "income", "payment"]
    assert "expected income on Sep 12" in r["warning_message"]


def test_salary_after_the_due_date_does_not_help():
    r = run("1000", [pay("Netflix", "2000", 15)], [salary(20)])
    assert r["risk_level"] == "SHORTFALL" and r["expected_income"] == D("0")


def test_below_safety_buffer_is_watch():
    r = run("5000", [pay("Netflix", "2000", 15)])
    assert r["risk_level"] == "WATCH" and r["projected_balance"] == D("3000")
    assert "₹5,000 safety buffer" in r["warning_message"]


def test_multiple_payments_total_and_order():
    r = run("50000", [pay("Netflix", "2000", 15), pay("Electricity", "1500", 20, "Utilities")])
    assert r["risk_level"] == "SAFE" and r["upcoming_amount"] == D("3500")
    assert [p["merchant"] for p in r["upcoming_payments"]] == ["Netflix", "Electricity"]


def test_savings_target_at_risk():
    savings = {"target": D("25000"), "income": D("100000"), "estimated_savings": D("35000")}  # 100k income - 65k spent
    r = run("60000", [pay("Insurance", "8000", 20, "Insurance")], savings=savings, cycle_end=datetime(2026, 9, 30, tzinfo=TZ))
    assert r["risk_level"] == "AT_RISK" and r["savings_impact"]["status"] == "TIGHT"
    assert "₹8,000" in r["savings_impact"]["message"] and "₹25,000" in r["savings_impact"]["message"]


def test_spending_pace_warning():
    spending = {"limit": D("75000"), "spent": D("60000"), "basis": "test"}
    r = run("90000", [pay("Rent", "10000", 20, "Housing")], spending=spending, cycle_end=datetime(2026, 9, 25, tzinfo=TZ))
    assert r["risk_level"] == "AT_RISK" and r["budget_impact"]["status"] == "TIGHT"
    assert r["budget_impact"]["remaining"] == D("5000")


def test_payment_after_cycle_end_does_not_touch_savings():
    savings = {"target": D("25000"), "income": D("100000"), "estimated_savings": D("26000")}
    r = run("60000", [pay("Insurance", "8000", 28, "Insurance")], savings=savings, cycle_end=datetime(2026, 9, 20, tzinfo=TZ))
    assert r["savings_impact"]["status"] == "UNAFFECTED" and r["risk_level"] == "SAFE"


def test_nothing_upcoming_is_safe():
    r = run("1000", [])
    assert r["risk_level"] == "SAFE" and r["upcoming_amount"] == D("0") and "No recurring payments" in r["warning_message"]


def test_demo_scenario_end_to_end(conn):
    r = setup_cashflow_scenario(conn, DEMO_USER, DEMO_ACCOUNT)
    assert r["risk_level"] == "SHORTFALL"
    assert r["current_balance"] == D("1000") and r["shortfall_amount"] == D("1000")
    assert r["expected_income"] == D("0")
    first = r["upcoming_payments"][0]
    assert first["merchant"] == "CloudVault Pro" and first["amount"] == D("2000") and first["days_remaining"] == 5
    assert "adding funds" in r["suggested_action"]
    # read-only: checking again changes nothing
    assert check_upcoming_financial_risk(conn, DEMO_USER, DEMO_ACCOUNT)["shortfall_amount"] == D("1000")


def test_seeded_demo_user_gets_a_sensible_answer(conn):
    r = check_upcoming_financial_risk(conn, DEMO_USER, DEMO_ACCOUNT)
    assert r["risk_level"] in {"SAFE", "WATCH", "AT_RISK", "SHORTFALL"}
    assert all(p["due_at"] >= r["as_of"] - timedelta(days=7) for p in r["upcoming_payments"])


# ---- What-if, streak, briefing (need the seeded database)

def test_whatif_is_hypothetical_and_can_flip_the_risk_level(conn):
    from app.services.engagement import simulate_purchase
    setup_cashflow_scenario(conn, DEMO_USER, DEMO_ACCOUNT)  # balance 1,000 vs 2,000 due: already SHORTFALL
    before = conn.execute("select count(*) as n from transactions where user_id = %s", (DEMO_USER,)).fetchone()["n"]
    r = simulate_purchase(conn, DEMO_USER, DEMO_ACCOUNT, D("500"), "Headphones", 0)
    assert r["risk_before"] == "SHORTFALL" and r["risk_after"] == "SHORTFALL"
    assert r["shortfall_after"] == D("1500")
    assert conn.execute("select count(*) as n from transactions where user_id = %s", (DEMO_USER,)).fetchone()["n"] == before


def test_whatif_small_purchase_on_a_healthy_account_is_fine(conn):
    from app.services.engagement import simulate_purchase
    r = simulate_purchase(conn, DEMO_USER, DEMO_ACCOUNT, D("100"), "Coffee beans", 1)
    assert r["risk_after"] == r["risk_before"] and "Hypothetical" in r["note"]


def test_streak_and_briefing_shape(conn):
    from app.services.engagement import build_briefing, spending_streak
    s = spending_streak(conn, DEMO_USER, DEMO_ACCOUNT)
    assert s["available"] and s["current_streak"] >= 0 and s["best_streak"] >= s["current_streak"]
    b = build_briefing(conn, DEMO_USER, DEMO_ACCOUNT, "roast")
    assert b["tone"] == "roast" and b["items"] and b["items"][0]["kind"] == "cashflow"
    assert build_briefing(conn, DEMO_USER, DEMO_ACCOUNT, "bogus")["tone"] == "chill"


def test_tone_only_changes_the_prompt_voice():
    from app.agent.prompts import SYSTEM_PROMPT, system_prompt
    for tone in ("chill", "coach", "roast", "unknown"):
        assert system_prompt(tone).startswith(SYSTEM_PROMPT)
    assert "teasing" in system_prompt("roast") and "teasing" not in system_prompt("chill")
