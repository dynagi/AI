"""Goal analysis (pure): purchase goal, emergency fund, projection, priority allocation. No database."""

from datetime import date, datetime
from decimal import Decimal

from app.services.goals import Pace, analyze_goals, combine_pace

D = Decimal
TODAY = date(2026, 9, 30)


def goal(name, target, current, target_date, gtype="PURCHASE", priority="MEDIUM", status="ACTIVE", gid=None):
    return {
        "id": gid or name, "name": name, "goal_type": gtype, "target_amount": D(str(target)), "current_amount": D(str(current)),
        "target_date": target_date, "priority": priority, "status": status, "created_at": datetime(2026, 1, 1),
    }


def pace(monthly):
    m = D(str(monthly))
    return Pace(history_average=m, history_cycles=3, current_projected=None, effective=m, basis="history")


def one(goals, p):
    return analyze_goals(goals, p, TODAY)["goals"][0]


def test_purchase_goal_matches_the_spec_example():
    # Laptop 60,000, saved 20,000, 6 months left, saving 8,000/month -> needs ~6,667/month -> ON_TRACK
    g = one([goal("Laptop", 60000, 20000, date(2027, 3, 31))], pace(8000))
    assert g["remaining_amount"] == D("40000.00")
    assert g["progress_percent"] == 33.3
    assert D("6600") < g["required_monthly_contribution"] < D("6800")
    assert g["status"] == "ON_TRACK"
    assert g["projected_completion_date"] is not None and g["projected_completion_date"] < date(2027, 3, 31)
    assert "on track" in g["message"]


def test_goal_is_flagged_when_the_current_pace_is_too_low():
    # Needs ~10,000/month but only 7,000 is available: "may not be reached by the target date".
    g = one([goal("Trip", 59000, 0, date(2027, 3, 31), "TRAVEL")], pace(7000))
    assert D("9800") < g["required_monthly_contribution"] < D("10000")
    assert g["status"] == "AT_RISK"  # 7,000 covers 70%+ of the requirement
    assert "may not be reached" in g["message"] and "₹7,000" in g["message"]
    lower = one([goal("Trip", 59000, 0, date(2027, 3, 31), "TRAVEL")], pace(3000))
    assert lower["status"] == "BEHIND"


def test_emergency_fund_progress_and_type():
    g = one([goal("Emergency Fund", 150000, 70000, date(2027, 6, 30), "EMERGENCY_FUND", "HIGH")], pace(20000))
    assert g["progress_percent"] == 46.7 and g["goal_type"] == "EMERGENCY_FUND"
    assert g["remaining_amount"] == D("80000.00") and g["status"] == "ON_TRACK"


def test_completed_goal():
    g = one([goal("Done", 1000, 1000, date(2027, 1, 1))], pace(0))
    assert g["status"] == "COMPLETED" and g["remaining_amount"] == 0 and g["progress_percent"] == 100.0


def test_goals_compete_for_the_same_savings_by_priority():
    goals = [
        goal("Trip", 24000, 0, date(2027, 9, 30), "TRAVEL", "MEDIUM", gid="trip"),
        goal("Emergency", 48000, 0, date(2027, 9, 30), "EMERGENCY_FUND", "HIGH", gid="ef"),
    ]
    out = {g["id"]: g for g in analyze_goals(goals, pace(4100), TODAY)["goals"]}
    # Emergency needs ~4,000/month and is funded first; the trip needs ~2,000 and gets what is left (nothing).
    assert out["ef"]["status"] == "ON_TRACK" and out["ef"]["allocated_monthly_savings"] > D("4000")
    assert out["trip"]["status"] == "BEHIND" and "higher-priority" in out["trip"]["message"]


def test_combined_requirement_is_reported():
    goals = [goal("A", 12000, 0, date(2027, 9, 30), gid="a"), goal("B", 12000, 0, date(2027, 9, 30), gid="b")]
    res = analyze_goals(goals, pace(1500), TODAY)
    assert res["combined"]["active_goals"] == 2
    assert res["combined"]["total_required_monthly"] > res["combined"]["savings_pace_monthly"]


def test_paused_goal_is_left_out_of_the_pace_analysis():
    g = one([goal("Paused", 60000, 0, date(2027, 3, 31), status="PAUSED")], pace(50000))
    assert g["status"] == "PAUSED" and g["allocated_monthly_savings"] is None


def test_no_history_means_no_invented_projection():
    p = combine_pace([], None)
    g = one([goal("Laptop", 60000, 20000, date(2027, 3, 31))], p)
    assert g["status"] is None and g["reason"] == "insufficient_history" and g["projected_completion_date"] is None
    assert "not enough" in g["message"].lower()


def test_passed_target_date_is_behind():
    g = one([goal("Late", 1000, 100, date(2026, 8, 1))], pace(50000))
    assert g["status"] == "BEHIND" and g["days_remaining"] < 0


def test_spending_spike_this_cycle_lowers_the_pace_and_therefore_the_status():
    # History says 50,000/month, but this cycle is projected to save only 3,000: the lower figure governs.
    p = combine_pace([D("50000"), D("50000")], D("3000"))
    assert p.effective == D("3000") and p.basis == "history_and_current_cycle"
    g = one([goal("Laptop", 60000, 20000, date(2027, 3, 31))], p)
    assert g["status"] == "BEHIND"
    assert "₹3,000" in g["message"]


def test_a_cycle_that_saves_nothing_is_described_plainly_not_as_negative_savings():
    p = combine_pace([D("50000")], D("-22000"))
    g = one([goal("Laptop", 60000, 20000, date(2027, 3, 31))], p)
    assert g["status"] == "BEHIND" and g["available_monthly_savings"] == D("0.00")
    assert "on course to save nothing" in g["message"] and "-₹22,000" in g["message"]
    assert "saving approximately -" not in g["message"]
