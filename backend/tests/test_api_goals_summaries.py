"""HTTP tests for goals, budgets overview, summaries, action items, insights overview, trends; and grounding of the new agent tools."""

import json
import time
from contextlib import nullcontext
from decimal import Decimal

import jwt
import pytest
from fastapi.testclient import TestClient

from app.agent.tools import ToolContext, build_tools
from app.services import goals as goals_svc
from app.services import summaries as summ
from tests.conftest import DEMO_ACCOUNT, DEMO_USER, make_user

SECRET = "test-secret-test-secret-test-secret-123456"
D = Decimal


def token(uid):
    return jwt.encode({"sub": uid, "email": "x@example.test", "aud": "authenticated", "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")


def H(uid=DEMO_USER):
    return {"Authorization": f"Bearer {token(uid)}"}


@pytest.fixture()
def client(dsn, monkeypatch):
    from app import db
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    db.close_pool()
    db.open_pool(dsn, min_size=1, max_size=4)
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    db.close_pool()
    get_settings.cache_clear()


# --------------------------------------------------------------------- goals


def test_goals_api_purchase_and_emergency_fund_flow(client):
    r = client.get("/goals", headers=H()).json()
    assert {g["name"] for g in r["goals"]} == {"New Laptop", "Emergency Fund"}
    assert set(r["goal_types"]) == {"PURCHASE", "EMERGENCY_FUND", "TRAVEL", "EDUCATION", "CUSTOM"}
    assert r["combined"]["active_goals"] == 2

    made = client.post("/goals", headers=H(), json={"name": "Europe trip", "goal_type": "TRAVEL", "target_amount": 120000,
                                                    "current_amount": 10000, "target_date": "2027-08-01", "priority": "HIGH"})
    assert made.status_code == 200 and made.json()["goal_type"] == "TRAVEL"
    gid = made.json()["id"]

    c = client.post(f"/goals/{gid}/contributions", headers=H(), json={"amount": 5000, "notes": "bonus"}).json()
    assert float(c["goal"]["current_amount"]) == 15000
    detail = client.get(f"/goals/{gid}", headers=H()).json()
    assert detail["goal"]["progress_percent"] == 12.5 and len(detail["contributions"]) == 1

    assert client.patch(f"/goals/{gid}", headers=H(), json={"status": "PAUSED"}).json()["status"] == "PAUSED"
    assert client.patch(f"/goals/{gid}", headers=H(), json={"target_amount": 130000, "name": "Europe 2027"}).json()["name"] == "Europe 2027"
    assert client.patch(f"/goals/{gid}", headers=H(), json={"status": "COMPLETED"}).json()["status"] == "COMPLETED"
    # the contribution never touched the ledger
    assert float(client.get("/dashboard", headers=H()).json()["account"]["current_balance"]) == 35000


def test_goals_api_validation_and_isolation(client, conn):
    assert client.post("/goals", headers=H(), json={"name": "x", "goal_type": "LOTTERY", "target_amount": 10, "target_date": "2027-01-01"}).status_code == 422
    assert client.post("/goals", headers=H(), json={"name": "x", "target_amount": -5, "target_date": "2027-01-01"}).status_code == 422
    assert client.post("/goals", headers=H(), json={"name": "x", "target_amount": 5, "target_date": "not-a-date"}).status_code == 422
    other = make_user(conn)
    conn.commit()
    gid = client.get("/goals", headers=H()).json()["goals"][0]["id"]
    assert client.get("/goals", headers=H(other)).json()["goals"] == []
    assert client.get(f"/goals/{gid}", headers=H(other)).status_code == 404
    assert client.patch(f"/goals/{gid}", headers=H(other), json={"status": "PAUSED"}).status_code == 404
    assert client.post(f"/goals/{gid}/contributions", headers=H(other), json={"amount": 1}).status_code == 404
    assert client.get("/goals", headers=H()).json()["goals"][0]["lifecycle"] == "ACTIVE"  # untouched


# ------------------------------------------------------------------- budgets


def test_budgets_overview_shape_and_commitments(client):
    r = client.get("/budgets", headers=H()).json()
    assert {b["category"] for b in r["budgets"]} == {"Food", "Shopping", "Transport", "Entertainment"}
    assert set(r["totals"]) == {"total_budget", "spent", "remaining", "committed", "projected"}
    assert float(r["totals"]["total_budget"]) == 19000
    assert r["commitments"]["budget_basis"] == "savings_target"
    assert set(r["budgets"][0]) >= {"status", "committed", "projected_spend", "percent_used", "upcoming_recurring"}


# ----------------------------------------------------------------- summaries


def test_summaries_api_list_detail_generate_and_actions(client):
    listing = client.get("/summaries", headers=H()).json()
    assert len(listing["summaries"]) == 5 and listing["open_actions"]
    first = listing["summaries"][0]
    assert first["is_final"] and first["open_actions"] > 0
    detail = client.get(f"/summaries/{first['id']}", headers=H()).json()
    assert detail["content"]["observations"] and detail["actions"]

    aid = detail["actions"][0]["id"]
    assert client.patch(f"/summary-actions/{aid}", headers=H(), json={"status": "COMPLETED"}).json()["status"] == "COMPLETED"
    assert client.patch(f"/summary-actions/{aid}", headers=H(), json={"status": "BOGUS"}).status_code == 422
    kept = client.get(f"/summaries/{first['id']}", headers=H()).json()["actions"]
    assert next(a for a in kept if a["id"] == aid)["status"] == "COMPLETED"  # kept, not deleted

    gen = client.post("/summaries/generate", headers=H(), json={}).json()  # current cycle
    assert gen["is_final"] is False and float(gen["expense_total"]) == 42500
    assert len(client.get("/summaries", headers=H()).json()["summaries"]) == 6


def test_summaries_api_isolation(client, conn):
    other = make_user(conn)
    conn.commit()
    sid = client.get("/summaries", headers=H()).json()["summaries"][0]["id"]
    aid = client.get(f"/summaries/{sid}", headers=H()).json()["actions"][0]["id"]
    assert client.get("/summaries", headers=H(other)).json()["summaries"] == []
    assert client.get(f"/summaries/{sid}", headers=H(other)).status_code == 404
    assert client.patch(f"/summary-actions/{aid}", headers=H(other), json={"status": "DISMISSED"}).status_code == 404
    assert client.post("/summaries/generate", headers=H(other), json={}).status_code == 404  # they have no cycle
    cycle_id = client.get("/cycles", headers=H()).json()["cycles"][0]["id"]
    assert client.post("/summaries/generate", headers=H(other), json={"cycle_id": cycle_id}).status_code == 404


def test_new_cycle_generates_summary_and_alert_over_http(client):
    client.post("/demo/transactions", headers=H(), json={"type": "SALARY", "amount": 100000})
    listing = client.get("/summaries", headers=H()).json()
    assert len(listing["summaries"]) == 6
    alerts = client.get("/alerts", headers=H()).json()["alerts"]
    assert {"NEW_CYCLE", "SUMMARY_READY", "SAVINGS_TARGET_NEEDED"} <= {a["alert_type"] for a in alerts}


# ------------------------------------------------------- insights and trends


def test_insights_overview_links_to_real_data(client):
    o = client.get("/insights/overview", headers=H()).json()
    assert len(o["trends"]) == 6 and o["trends"][-1]["status"] == "ACTIVE"
    assert {u["type"] for u in o["unusual_activity"]} >= {"CATEGORY_SPIKE"}
    assert len(o["recurring"]) == 7 and o["upcoming_obligations"]["within_days"] == 30
    assert o["savings"]["cycle"] and o["insights"]
    for i in o["insights"]:
        assert i["evidence"]
    cats = {r["merchant"] for r in o["recurring"]}
    assert not any("insurance" in c.lower() or "emi" in c.lower() for c in cats)  # nothing invented


def test_trends_and_daily_endpoints(client):
    t = client.get("/trends?limit=4", headers=H()).json()["cycles"]
    assert len(t) == 4 and t[-1]["status"] == "ACTIVE"
    d = client.get("/spending/daily?days=5", headers=H()).json()
    assert len(d["days"]) == 5 and d["yesterday"] is not None


def test_dashboard_carries_goals_commitments_and_summary_pointers(client):
    d = client.get("/dashboard", headers=H()).json()
    assert {g["name"] for g in d["goals"]} == {"New Laptop", "Emergency Fund"}
    assert d["commitments"]["budget_basis"] == "savings_target"
    assert d["latest_summary"]["id"] and d["open_action_count"] > 0
    assert d["savings"]["capacity_message"].startswith("You have ")


# ---------------------------------------------------- agent tool grounding


def tool(conn, name, user_id=DEMO_USER, **args):
    ctx = ToolContext(user_id=user_id, connect=lambda: nullcontext(conn))
    return next(t for t in build_tools(ctx) if t.name == name).invoke(args)


def test_goal_tools_return_database_values(conn):
    g = tool(conn, "get_goal_progress", goal="laptop")
    assert g["count"] == 1 and g["goals"][0]["name"] == "New Laptop"
    assert g["goals"][0]["remaining_amount"] == "40000.00" and g["goals"][0]["remaining_amount_inr"] == "₹40,000"
    ef = tool(conn, "get_goal_progress", goal="emergency fund")["goals"][0]
    assert ef["progress_percent"] == 46.7 and ef["current_amount_inr"] == "₹70,000"
    proj = tool(conn, "get_goal_projection", goal="laptop")
    assert proj["goals"][0]["projected_completion_date"] and proj["combined"]["total_required_monthly"]
    assert tool(conn, "get_goal_progress", goal="yacht")["count"] == 0  # no invented goal
    assert tool(conn, "get_financial_goals")["combined"]["active_goals"] == 2


def test_budget_summary_and_trend_tools_return_database_values(conn):
    c = tool(conn, "get_budget_commitments")
    assert c["budget_basis"] == "savings_target" and c["monthly_budget"] == "75000.00" and c["already_spent"] == "42500.00"
    assert "calculation" in c
    s = tool(conn, "get_monthly_summary", cycle="previous")
    assert s["expenses"] == "46200.00" and s["is_final"] is True and s["top_category"] == "Housing"
    assert any("Shopping spending increased" in o for o in s["observations"]) and s["action_items"]
    cur = tool(conn, "get_monthly_summary", cycle="current")
    assert cur["is_final"] is False and cur["expenses"] == "42500.00"
    t = tool(conn, "get_monthly_trends", limit=3)
    assert [x["expenses"] for x in t["cycles"]] == ["44100.00", "46200.00", "42500.00"]
    assert tool(conn, "get_category_breakdown")["categories"][0]["category"] == "Housing"
    assert tool(conn, "get_daily_spending", days=3)["days"]
    items = tool(conn, "get_monthly_action_items")
    assert items["count"] > 0 and all(i["status"] == "OPEN" for i in items["items"])


def test_new_tools_never_leak_across_users(conn):
    other = make_user(conn)
    from app.services.accounts import create_manual_account

    create_manual_account(conn, other, "Other", D("10"))
    for name, args in [("get_financial_goals", {}), ("get_goal_progress", {}), ("get_monthly_action_items", {})]:
        out = tool(conn, name, user_id=other, **args)
        blob = json.dumps(out)
        assert "Laptop" not in blob and "Emergency" not in blob and "Shopping" not in blob, (name, out)
    assert tool(conn, "get_budget_commitments", user_id=other)["error"] == "no_cycle"
    summary = tool(conn, "get_monthly_summary", user_id=other, cycle="previous")
    assert summary.get("error") == "no_cycle"
    demo_cycle = str(summ.list_summaries(conn, DEMO_USER)[0]["financial_cycle_id"])
    assert tool(conn, "get_monthly_summary", user_id=other, cycle=demo_cycle).get("error") == "no_cycle"
