"""Goals, budgets, commitments, recurring/anomaly detection, monthly summaries and action items,
against real PostgreSQL with the seeded demo data."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.demo.dataset import DEMO_NEXT_SALARY_TIME, generate_demo_history
from app.services import goals as goals_svc
from app.services import queries
from app.services import summaries as summ
from app.services.alerts import list_alerts
from app.services.analytics import daily_spending, monthly_trends, unusual_for_cycle
from app.services.budgets import budget_commitments, budget_status, set_budget
from app.services.comparison import progress_vs_previous, cycle_summary
from app.services.cycle_state import set_target
from app.services.dashboard import build_dashboard
from app.services.demo_service import ensure_analytics, simulate_transaction
from app.services.recurring import detect_from_rows
from tests.conftest import DEMO_ACCOUNT, DEMO_USER, make_user

D = Decimal
IST = timezone(timedelta(hours=5, minutes=30))


def sim(conn, ttype, amount, **kw):
    return simulate_transaction(conn, user_id=DEMO_USER, account_id=DEMO_ACCOUNT, transaction_type=ttype, amount=D(str(amount)), **kw)


def active(conn):
    return queries.active_cycle(conn, DEMO_USER, DEMO_ACCOUNT)


# ------------------------------------------------------------------- goals


def test_seeded_goals_match_the_spec_examples(conn):
    ov = goals_svc.goals_overview(conn, DEMO_USER, DEMO_ACCOUNT)
    by = {g["name"]: g for g in ov["goals"]}
    laptop, ef = by["New Laptop"], by["Emergency Fund"]
    assert laptop["goal_type"] == "PURCHASE" and laptop["target_amount"] == D("60000.00") and laptop["current_amount"] == D("20000.00")
    assert laptop["remaining_amount"] == D("40000.00") and laptop["progress_percent"] == 33.3
    assert D("6500") < laptop["required_monthly_contribution"] < D("6800")  # ~6,667/month over ~6 months
    assert ef["goal_type"] == "EMERGENCY_FUND" and ef["progress_percent"] == 46.7 and ef["remaining_amount"] == D("80000.00")
    assert laptop["status"] == "ON_TRACK" and ef["status"] == "ON_TRACK"  # the seeded cycles save ~55k a month
    assert "Based on your transaction history" in laptop["message"]
    assert ov["combined"]["total_required_monthly"] > 0


def test_goal_lifecycle_and_contributions_do_not_touch_the_ledger(conn):
    balance_before = build_dashboard(conn, DEMO_USER)["account"]["current_balance"]
    expenses_before = active(conn)["expense_total"]
    g = goals_svc.create_goal(conn, DEMO_USER, name="Goa trip", goal_type="TRAVEL", target_amount=D("30000"),
                              current_amount=D("5000"), target_date=date(2027, 2, 1), priority="LOW")
    contribution, updated = goals_svc.add_contribution(conn, DEMO_USER, str(g["id"]), D("5000"), "from bonus")
    assert updated["current_amount"] == D("10000.00") and contribution["amount"] == D("5000.00")
    assert build_dashboard(conn, DEMO_USER)["account"]["current_balance"] == balance_before  # not an expense
    assert active(conn)["expense_total"] == expenses_before
    # pause / edit / complete
    assert goals_svc.update_goal(conn, DEMO_USER, str(g["id"]), {"status": "PAUSED"})["status"] == "PAUSED"
    assert goals_svc.update_goal(conn, DEMO_USER, str(g["id"]), {"name": "Goa trip 2027", "target_amount": D("32000")})["target_amount"] == D("32000.00")
    done = goals_svc.update_goal(conn, DEMO_USER, str(g["id"]), {"status": "COMPLETED"})
    assert done["status"] == "COMPLETED" and done["completed_at"] is not None
    # a contribution that reaches the target completes the goal automatically
    g2 = goals_svc.create_goal(conn, DEMO_USER, name="Course", goal_type="EDUCATION", target_amount=D("1000"),
                               current_amount=D("900"), target_date=date(2027, 1, 1))
    _, finished = goals_svc.add_contribution(conn, DEMO_USER, str(g2["id"]), D("100"))
    assert finished["status"] == "COMPLETED"


def test_goal_validation(conn):
    with pytest.raises(goals_svc.GoalError):
        goals_svc.create_goal(conn, DEMO_USER, name="x", goal_type="LOTTERY", target_amount=D("1"), current_amount=D("0"), target_date=date(2027, 1, 1))
    with pytest.raises(goals_svc.GoalError):
        goals_svc.add_contribution(conn, DEMO_USER, str(goals_svc.list_goals(conn, DEMO_USER)[0]["id"]), D("0"))
    with pytest.raises(goals_svc.GoalNotFound):
        goals_svc.get_goal(conn, DEMO_USER, "00000000-0000-0000-0000-000000000000")


def test_a_big_spend_this_cycle_makes_goals_behind_because_it_lowers_the_savings_pace(conn):
    sim(conn, "SALARY", 100000)
    sim(conn, "EXPENSE", 99000, merchant="Croma Electronics")  # this cycle now saves almost nothing
    ov = goals_svc.goals_overview(conn, DEMO_USER, DEMO_ACCOUNT)
    assert ov["combined"]["pace"]["basis"] == "history_and_current_cycle"
    assert ov["combined"]["savings_pace_monthly"] < D("5000")
    assert {g["status"] for g in ov["goals"]} <= {"AT_RISK", "BEHIND"}
    alerts = [a for a in list_alerts(conn, DEMO_USER, limit=50) if a["alert_type"] == "GOAL_AT_RISK"]
    assert alerts and "may not be reached" in alerts[0]["message"]


def test_goals_are_private_to_their_owner(conn):
    other = make_user(conn)
    assert goals_svc.list_goals(conn, other) == []
    gid = str(goals_svc.list_goals(conn, DEMO_USER)[0]["id"])
    with pytest.raises(goals_svc.GoalNotFound):
        goals_svc.get_goal(conn, other, gid)
    with pytest.raises(goals_svc.GoalNotFound):
        goals_svc.add_contribution(conn, other, gid, D("10"))
    with pytest.raises(goals_svc.GoalNotFound):
        goals_svc.update_goal(conn, other, gid, {"status": "PAUSED"})


# ------------------------------------------------ savings target scenarios


def test_spec_scenario_amazon_at_1205(conn):
    sim(conn, "SALARY", 100000)
    sim(conn, "EXPENSE", 160)
    sim(conn, "TRANSFER_IN", 1000)
    sim(conn, "EXPENSE", 2500, merchant="Amazon")
    d = build_dashboard(conn, DEMO_USER)
    assert d["account"]["current_balance"] == D("133340.00")
    assert d["cycle"]["expenses"] == D("2660.00") and d["cycle"]["income"] == D("100000.00")
    assert [t["timestamp"].astimezone(IST).strftime("%H:%M") for t in d["recent_transactions"][:3]] == ["12:05", "11:40", "11:35"]


def test_spec_savings_scenario_capacity_and_risk(conn):
    sim(conn, "SALARY", 100000)
    set_target(conn, DEMO_USER, str(active(conn)["id"]), D("25000"))
    sim(conn, "EXPENSE", 60000, merchant="Croma Electronics")
    s = build_dashboard(conn, DEMO_USER)["savings"]
    assert s["planned_spend_limit"] == "75000.00" and s["remaining_spend_capacity"] == "15000.00"
    assert s["capacity_message"] == "You have ₹15,000 of spending capacity remaining if you want to maintain your ₹25,000 savings target."
    sim(conn, "EXPENSE", 6000, merchant="Amazon")
    d = build_dashboard(conn, DEMO_USER)
    assert d["savings"]["remaining_spend_capacity"] == "9000.00"
    risk = [a for a in d["alerts"] if a["alert_type"] == "SAVINGS_AT_RISK"]
    assert risk and "₹66,000" in risk[0]["message"] and "₹75,000" in risk[0]["message"]  # actual numbers, not vague text
    assert any(a["alert_type"] == "HIGH_SPENDING" for a in d["alerts"])


def test_spec_historical_scenario_previous_42500_vs_current_18200(conn):
    sim(conn, "SALARY", 100000)
    sim(conn, "EXPENSE", 18200, merchant="Amazon")
    d = build_dashboard(conn, DEMO_USER)
    pv = d["progress_vs_previous"]
    assert (pv["previous"], pv["current"], pv["remaining"]) == (D("42500.00"), D("18200.00"), D("24300.00"))
    assert pv["difference"] == D("-24300.00") and pv["change_percent"] == -57.2
    assert "₹24,300" in pv["message"]
    sim(conn, "EXPENSE", 26650, merchant="Amazon")  # 44,850 in total: 2,350 over last cycle's 42,500
    pv2 = build_dashboard(conn, DEMO_USER)["progress_vs_previous"]
    assert pv2["exceeded_by"] == D("2350.00") and "exceeded last cycle's total by ₹2,350" in pv2["message"]
    # and the previous cycle stays queryable
    assert cycle_summary(conn, DEMO_USER, queries.previous_cycle(conn, DEMO_USER, active(conn)))["expenses"] == D("42500.00")


# ----------------------------------------------- budgets and commitments


def test_budget_utilization_and_statuses(conn):
    rows = {b["category"]: b for b in budget_status(conn, DEMO_USER, DEMO_ACCOUNT)}
    food = rows["Food"]  # seeded budget 7,000; the seeded cycle spent 6,585 on food
    assert food["amount"] == D("7000.00") and food["spent"] == D("6585.00") and food["remaining"] == D("415.00")
    assert food["percent_used"] == 94.1 and food["status"] == "AT_RISK"
    assert rows["Entertainment"]["status"] == "ON_TRACK"
    set_budget(conn, DEMO_USER, "Shopping", D("3000"))
    shop = {b["category"]: b for b in budget_status(conn, DEMO_USER, DEMO_ACCOUNT)}["Shopping"]
    assert shop["spent"] == D("3600.00") and shop["status"] == "OVER_BUDGET" and shop["remaining"] == D("-600.00")
    assert set(shop) >= {"upcoming_recurring", "committed", "projected_spend", "percent_used"}


def test_no_budget_shown_for_categories_without_a_budget(conn):
    assert {b["category"] for b in budget_status(conn, DEMO_USER, DEMO_ACCOUNT)} == {"Food", "Shopping", "Transport", "Entertainment"}


def test_budget_commitments_separate_spent_from_expected(conn):
    sim(conn, "SALARY", 100000)
    sim(conn, "EXPENSE", 160)
    set_target(conn, DEMO_USER, str(active(conn)["id"]), D("25000"))
    c = budget_commitments(conn, DEMO_USER, DEMO_ACCOUNT)
    assert c["budget_basis"] == "savings_target" and c["monthly_budget"] == D("75000.00")
    assert c["already_spent"] == D("160.00")
    items = {i["merchant"]: i["amount"] for i in c["upcoming_recurring_items"]}
    assert items["Landlord - Sharma Properties"] == D("15000.00") and "Netflix" in items and "Spotify" in items
    assert c["upcoming_recurring_expected"] == sum(items.values())
    assert c["committed_total"] == c["already_spent"] + c["upcoming_recurring_expected"]
    assert c["remaining_flexible_capacity"] == c["monthly_budget"] - c["committed_total"]
    assert "already spent" in c["calculation"] and c["percent_of_budget_committed"] > 20


def test_commitments_before_the_new_salary_do_not_double_count_paid_bills(conn):
    c = budget_commitments(conn, DEMO_USER, DEMO_ACCOUNT)  # seeded state: every bill is already paid in this cycle
    assert c["upcoming_recurring_expected"] == D("0.00")
    assert c["committed_total"] == c["already_spent"]


def test_commitments_fall_back_to_category_budgets_without_a_target(conn):
    c = budget_commitments(conn, DEMO_USER, DEMO_ACCOUNT)
    assert c["budget_basis"] == "savings_target"  # the seeded active cycle has a 25,000 target
    sim(conn, "SALARY", 100000)  # the new cycle has no target yet
    c2 = budget_commitments(conn, DEMO_USER, DEMO_ACCOUNT)
    assert c2["budget_basis"] == "category_budgets" and c2["monthly_budget"] == D("19000.00")  # 7000+6000+4000+2000


# --------------------------------------------- recurring and anomaly checks


def _monthly(merchant, amount, n, start=datetime(2026, 1, 5, tzinfo=IST), step=30, category="Subscriptions"):
    return [{"id": f"{merchant}-{i}", "timestamp": start + timedelta(days=step * i), "description": merchant.upper(),
             "merchant": merchant, "amount": D(str(amount)), "category": category} for i in range(n)]


def test_recurring_detection_needs_real_evidence():
    found = {r["merchant"]: r for r in detect_from_rows(sorted(_monthly("Netflix", 649, 4) + _monthly("Gym", 1200, 3, step=31), key=lambda r: r["timestamp"]))}
    assert set(found) == {"Netflix", "Gym"}
    assert found["Netflix"]["frequency"] == "monthly" and found["Netflix"]["average_amount"] == D("649") and found["Netflix"]["occurrences"] == 4
    assert found["Netflix"]["next_expected_payment"] > found["Netflix"]["last_payment"] and found["Netflix"]["confidence"] > D("0.8")
    assert detect_from_rows(_monthly("Spotify", 119, 2)) == []  # two payments are not enough
    irregular = [{"id": str(i), "timestamp": datetime(2026, 1, 1, tzinfo=IST) + timedelta(days=d), "description": "X", "merchant": "Cafe",
                  "amount": D("300"), "category": "Food"} for i, d in enumerate([0, 3, 40, 47])]
    assert detect_from_rows(irregular) == []  # uneven spacing
    varying = [{**r, "amount": D(str(a))} for r, a in zip(_monthly("Shop", 1, 4), [100, 900, 50, 700])]
    assert detect_from_rows(varying) == []  # amounts too different


def test_seeded_recurring_payments_are_exactly_the_real_ones(conn):
    merchants = {r["merchant"] for r in queries_recurring(conn)}
    assert merchants == {"Landlord - Sharma Properties", "Netflix", "Spotify", "Cult.fit", "ACT Fibernet", "Airtel", "BESCOM"}


def queries_recurring(conn):
    from app.services.recurring import list_recurring

    return list_recurring(conn, DEMO_USER)


def test_anomaly_detection_finds_the_seeded_healthcare_spike_but_not_rent(conn):
    found = unusual_for_cycle(conn, DEMO_USER, active(conn))
    spikes = [u for u in found if u["type"] == "CATEGORY_SPIKE"]
    assert [u["category"] for u in spikes] == ["Healthcare"] and spikes[0]["evidence"]["transaction_ids"]
    assert "%" in spikes[0]["message"]
    assert not any("Landlord" in u["message"] for u in found)  # recurring rent is not "unusual"


def test_trends_and_daily_spending(conn):
    trend = monthly_trends(conn, DEMO_USER, DEMO_ACCOUNT, 6)
    assert [t["expenses"] for t in trend] == [D(x) for x in ("38200.00", "41500.00", "39800.00", "44100.00", "46200.00", "42500.00")]
    assert trend[0]["change_vs_previous"] is None and trend[1]["change_vs_previous"] == D("3300.00")
    sim(conn, "SALARY", 100000)
    sim(conn, "EXPENSE", 160)
    sim(conn, "EXPENSE", 2500, merchant="Amazon")
    daily = daily_spending(conn, DEMO_USER, DEMO_ACCOUNT, 7)
    assert daily["today"]["total"] == D("2660.00") and daily["today"]["transactions"] == 2
    assert daily["yesterday"]["date"] == date(2026, 9, 29) and len(daily["days"]) == 7


# ------------------------------------------------------ monthly summaries


def test_seeded_summaries_exist_for_every_completed_cycle_and_match_the_ledger(conn):
    rows = summ.list_summaries(conn, DEMO_USER)
    assert len(rows) == 5 and all(r["is_final"] for r in rows)
    assert sorted(r["expense_total"] for r in rows) == [D(x) for x in ("38200.00", "39800.00", "41500.00", "44100.00", "46200.00")]
    latest = summ.get_summary(conn, DEMO_USER, str(rows[0]["id"]))  # newest first
    assert latest["expense_total"] == D("46200.00") and latest["previous_cycle_expenses"] == D("44100.00")
    assert latest["expense_change"] == D("2100.00") and latest["top_category"] == "Housing"
    assert latest["savings_total"] == D("55099.00")  # 100,000 - (46,200 - 1,299 refund)


def test_summary_contains_every_required_section(conn):
    s = summ.get_summary(conn, DEMO_USER, str(summ.list_summaries(conn, DEMO_USER)[0]["id"]))
    c = s["content"]
    assert set(c) >= {"overview", "top_categories", "previous_comparison", "recurring", "unusual_activity", "goals", "budgets", "observations"}
    assert len(c["top_categories"]) == 3 and c["overview"]["savings_target"] == "25000.00"
    assert c["previous_comparison"]["previous_expenses"] == "44100.00"
    assert c["recurring"]["active_recurring_payments"] == 7
    assert {g["name"] for g in c["goals"]} == {"New Laptop", "Emergency Fund"}
    assert s["savings_rate"] == D("55.10")
    texts = " ".join(o["text"] for o in c["observations"])
    assert "Shopping spending increased from ₹7,900 to ₹9,800" in texts


def test_action_items_are_specific_and_data_driven(conn):
    s = summ.get_summary(conn, DEMO_USER, str(summ.list_summaries(conn, DEMO_USER)[0]["id"]))
    assert s["actions"]
    generic = ("save more", "spend less", "be careful")
    for a in s["actions"]:
        assert a["priority"] in ("LOW", "MEDIUM", "HIGH") and a["status"] == "OPEN"
        assert any(ch.isdigit() for ch in a["description"]), a  # every action quotes real figures
        assert a["evidence"], a
        assert not any(g in a["description"].lower() for g in generic)
    review = next(a for a in s["actions"] if a["action_key"] == "review:Shopping")
    assert "₹1,900" in review["description"] and review["priority"] == "MEDIUM"
    assert {a["action_key"] for a in s["actions"]} >= {"goal:" + g["id"] for g in s["content"]["goals"]}


def test_completing_or_dismissing_actions_survives_regeneration(conn):
    sid = str(summ.list_summaries(conn, DEMO_USER)[0]["id"])
    acts = summ.get_summary(conn, DEMO_USER, sid)["actions"]
    a1, a2 = acts[0], acts[1]
    assert summ.set_action_status(conn, DEMO_USER, str(a1["id"]), "COMPLETED")["status"] == "COMPLETED"
    summ.set_action_status(conn, DEMO_USER, str(a2["id"]), "DISMISSED")
    cycle_id = str(summ.get_summary(conn, DEMO_USER, sid)["financial_cycle_id"])
    summ.generate_summary(conn, DEMO_USER, cycle_id)  # regenerate
    after = {a["action_key"]: a for a in summ.get_summary(conn, DEMO_USER, sid)["actions"]}
    assert after[a1["action_key"]]["status"] == "COMPLETED" and after[a2["action_key"]]["status"] == "DISMISSED"
    assert len(after) == len(acts)  # nothing deleted
    with pytest.raises(ValueError):
        summ.set_action_status(conn, DEMO_USER, str(a1["id"]), "DONE")


def test_summary_is_generated_automatically_when_a_cycle_closes(conn):
    before = {str(r["financial_cycle_id"]) for r in summ.list_summaries(conn, DEMO_USER)}
    closing = str(active(conn)["id"])
    assert closing not in before  # the running cycle has no final summary yet
    sim(conn, "SALARY", 100000)  # closes the 31 Aug cycle
    rows = summ.list_summaries(conn, DEMO_USER)
    new = next(r for r in rows if str(r["financial_cycle_id"]) == closing)
    assert new["is_final"] and new["expense_total"] == D("42500.00") and new["previous_cycle_expenses"] == D("46200.00")
    assert new["expense_change"] == D("-3700.00") and len(rows) == 6
    alerts = list_alerts(conn, DEMO_USER, limit=50)
    assert any(a["alert_type"] == "SUMMARY_READY" for a in alerts)
    assert summ.get_summary(conn, DEMO_USER, str(new["id"]))["actions"]


def test_generate_summary_on_demand_for_the_running_cycle(conn):
    sim(conn, "SALARY", 100000)
    cid = str(active(conn)["id"])
    row = summ.generate_summary(conn, DEMO_USER, cid)
    assert row["is_final"] is False and row["period_end"] is None and row["expense_total"] == D("0.00")
    sim(conn, "EXPENSE", 160)
    row2 = summ.generate_summary(conn, DEMO_USER, cid)
    assert row2["id"] == row["id"] and row2["expense_total"] == D("160.00")  # one summary per cycle, refreshed in place
    keys = {a["action_key"] for a in summ.get_summary(conn, DEMO_USER, str(row["id"]))["actions"]}
    assert "goal:" + str(goals_svc.list_goals(conn, DEMO_USER)[0]["id"]) in keys or any(k.startswith("goal:") for k in keys)


def test_summaries_are_private(conn):
    other = make_user(conn)
    sid = str(summ.list_summaries(conn, DEMO_USER)[0]["id"])
    assert summ.list_summaries(conn, other) == []
    with pytest.raises(summ.SummaryNotFound):
        summ.get_summary(conn, other, sid)
    aid = str(summ.get_summary(conn, DEMO_USER, sid)["actions"][0]["id"])
    with pytest.raises(summ.SummaryNotFound):
        summ.set_action_status(conn, other, aid, "COMPLETED")
    with pytest.raises(summ.SummaryNotFound):
        summ.generate_summary(conn, other, str(active(conn)["id"]))


def test_resetting_the_demo_drops_the_summary_of_the_reopened_cycle(conn):
    from app.services.demo_service import reset_simulated

    sim(conn, "SALARY", 100000)
    assert len(summ.list_summaries(conn, DEMO_USER)) == 6
    reset_simulated(conn, DEMO_USER, DEMO_ACCOUNT)
    assert len(summ.list_summaries(conn, DEMO_USER)) == 5  # the 31 Aug cycle is running again, so no final summary
