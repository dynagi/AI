"""HTTP-level tests: real JWT verification, real Postgres, seeded demo data."""

import time
from decimal import Decimal

import jwt
import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_ACCOUNT, DEMO_USER, make_user

SECRET = "test-secret-test-secret-test-secret-123456"


def token(user_id, email="x@example.test", exp=3600, secret=SECRET, aud="authenticated"):
    return jwt.encode({"sub": user_id, "email": email, "aud": aud, "exp": int(time.time()) + exp, "role": "authenticated"}, secret, algorithm="HS256")


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


def H(uid=DEMO_USER, **kw):
    return {"Authorization": f"Bearer {token(uid, **kw)}"}


def test_requires_a_valid_token(client):
    assert client.get("/dashboard").status_code == 401
    assert client.get("/dashboard", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/dashboard", headers=H(exp=-10)).status_code == 401
    assert client.get("/dashboard", headers=H(secret="wrong-secret-wrong-secret-wrong-secret-1")).status_code == 401
    assert client.get("/dashboard", headers=H(aud="anon")).status_code == 401
    assert client.get("/health").status_code == 200


def test_dashboard_for_demo_user(client):
    d = client.get("/dashboard", headers=H()).json()
    assert float(d["account"]["current_balance"]) == 35000
    assert float(d["cycle"]["expenses"]) == 42500
    assert d["cycle"]["status"] == "ACTIVE"
    assert len(d["recent_transactions"]) == 12
    assert d["alerts"] and d["insights"]  # populated by the SQL seed's first dashboard load


def test_realtime_demo_flow_over_http(client):
    """What the judge clicks: each call updates the ledger; a refetch (what a Realtime event triggers) shows it."""
    r = client.post("/demo/transactions", headers=H(), json={"type": "SALARY", "amount": 100000})
    assert r.status_code == 200 and r.json()["new_cycle_started"] is True
    d = client.get("/dashboard", headers=H()).json()
    assert (float(d["account"]["current_balance"]), float(d["cycle"]["income"]), float(d["cycle"]["expenses"])) == (135000, 100000, 0)

    r = client.post("/demo/transactions", headers=H(), json={"type": "EXPENSE", "amount": 160, "merchant": "Swiggy"}).json()
    assert float(r["balance"]) == 134840 and float(r["transaction"]["signed_amount"]) == -160
    d = client.get("/dashboard", headers=H()).json()
    assert float(d["account"]["current_balance"]) == 134840 and float(d["cycle"]["expenses"]) == 160
    assert d["recent_transactions"][0]["merchant"] == "Swiggy"

    client.post("/demo/transactions", headers=H(), json={"type": "TRANSFER_IN", "amount": 1000, "merchant": "Rahul"})
    d = client.get("/dashboard", headers=H()).json()
    assert float(d["account"]["current_balance"]) == 135840
    assert float(d["cycle"]["income"]) == 100000 and float(d["cycle"]["other_inflows"]) == 1000

    r = client.put("/savings/target", headers=H(), json={"target_amount": 25000})
    assert r.status_code == 200 and r.json()["status"] == "ON_TRACK"

    r = client.post("/demo/transactions", headers=H(), json={"type": "EXPENSE", "amount": 6000, "merchant": "Croma Electronics"}).json()
    assert any(a["type"] == "HIGH_SPENDING" for a in r["alerts"])
    cmp = client.get("/comparisons", headers=H()).json()["comparison"]
    assert float(cmp["a"]["expenses"]) == 42500 and float(cmp["b"]["expenses"]) == 6160
    assert float(cmp["expense_difference"]) == -36340

    assert client.post("/demo/reset", headers=H()).json()["removed"] == 4
    d = client.get("/dashboard", headers=H()).json()
    assert float(d["account"]["current_balance"]) == 35000 and float(d["cycle"]["expenses"]) == 42500


def test_users_cannot_see_or_touch_each_others_data(client, conn):
    other = make_user(conn)
    conn.commit()
    r = client.get("/dashboard", headers=H(other)).json()
    assert r["account"] is None  # sees none of the demo user's data
    assert client.get("/transactions", headers=H(other)).json()["transactions"] == []
    assert client.get("/cycles", headers=H(other)).json()["cycles"] == []
    demo_txn = client.get("/transactions?limit=1", headers=H()).json()["transactions"][0]["id"]
    assert client.patch(f"/transactions/{demo_txn}/category", headers=H(other), json={"category": "Travel"}).status_code == 404
    assert client.post(f"/accounts/{DEMO_ACCOUNT}/disconnect", headers=H(other)).status_code == 404
    assert client.post("/transactions", headers=H(other), json={"transaction_type": "EXPENSE", "amount": 5, "account_id": DEMO_ACCOUNT}).status_code == 404
    assert client.post("/demo/transactions", headers=H(other), json={"type": "EXPENSE", "amount": 5, "account_id": DEMO_ACCOUNT}).status_code == 404
    cyc = client.get("/cycles", headers=H()).json()["cycles"][0]["id"]
    assert client.get(f"/cycles/{cyc}", headers=H(other)).status_code == 404
    assert client.put("/savings/target", headers=H(other), json={"target_amount": 1, "cycle_id": cyc}).status_code == 404
    # and the demo user's data was not modified by any of the above
    assert float(client.get("/dashboard", headers=H()).json()["account"]["current_balance"]) == 35000


def test_manual_transaction_and_csv_use_the_same_pipeline(client):
    r = client.post("/transactions", headers=H(), json={"transaction_type": "EXPENSE", "amount": 500, "merchant": "Restaurant",
                                                         "timestamp": "2026-09-29T20:00:00+05:30"})
    assert r.status_code == 200 and float(r.json()["balance"]) == 34500
    csv = (b"date,description,merchant,amount,type,category,source,currency\n"
           b"2026-09-29,Coffee shop,Third Wave,250,expense,Food,csv,INR\n"
           b"2026-09-29,Money received from Asha,Asha,700,transfer,,csv,INR\n"
           b"not-a-date,bad row,,10,expense,,csv,INR\n")
    r = client.post("/transactions/csv", headers=H(), files={"file": ("t.csv", csv, "text/csv")}).json()
    assert r["inserted"] == 2 and r["malformed"] == 1 and r["errors"]
    again = client.post("/transactions/csv", headers=H(), files={"file": ("t.csv", csv, "text/csv")}).json()
    assert again["inserted"] == 0 and again["duplicates"] == 2  # re-import never duplicates
    bal = float(client.get("/dashboard", headers=H()).json()["account"]["current_balance"])
    assert bal == 35000 - 500 - 250 + 700
    txns = client.get("/transactions?limit=500", headers=H()).json()["transactions"]
    assert {t["source"] for t in txns} >= {"demo", "manual", "csv"}  # bank and manual data side by side
    asha = next(t for t in txns if t["merchant"] == "Asha")
    assert asha["transaction_type"] == "TRANSFER_IN"  # a transfer from a person is not salary/income


def test_csv_errors_are_friendly(client):
    assert client.post("/transactions/csv", headers=H(), files={"file": ("e.csv", b"foo,bar\n1,2\n", "text/csv")}).status_code == 400
    r = client.post("/transactions/csv", headers=H(), files={"file": ("e.csv", b"", "text/csv")})
    assert r.status_code == 400


def test_category_correction_is_learned(client):
    t = client.post("/transactions", headers=H(), json={"transaction_type": "EXPENSE", "amount": 90, "merchant": "Zed Store"}).json()["transaction"]
    assert t["category"] == "Other"
    assert client.patch(f"/transactions/{t['id']}/category", headers=H(), json={"category": "Shopping"}).status_code == 200
    t2 = client.post("/transactions", headers=H(), json={"transaction_type": "EXPENSE", "amount": 45, "merchant": "Zed Store"}).json()["transaction"]
    assert t2["category"] == "Shopping"


def test_new_user_can_connect_demo_bank_via_consent_flow(client, conn):
    uid = make_user(conn)
    conn.commit()
    c = client.post("/consents", headers=H(uid), json={"provider": "demo_bank"}).json()
    assert c["is_sandbox"] and "Sandbox" in c["account_label"] and c["data_requested"]
    assert client.post("/consents", headers=H(uid), json={"provider": "demo_bank"}).status_code == 200  # still pending: new request ok
    res = client.post(f"/consents/{c['consent_id']}/decision", headers=H(uid), json={"decision": "approve"}).json()
    assert res["status"] == "APPROVED" and res["inserted"] == 236
    d = client.get("/dashboard", headers=H(uid)).json()
    assert float(d["account"]["current_balance"]) == 35000 and float(d["cycle"]["expenses"]) == 42500
    assert client.post(f"/consents/{c['consent_id']}/decision", headers=H(uid), json={"decision": "approve"}).status_code == 409
    assert client.post("/consents", headers=H(uid), json={"provider": "demo_bank"}).status_code == 409  # already connected
    acct = client.get("/accounts", headers=H(uid)).json()["accounts"][0]["id"]
    assert client.post(f"/accounts/{acct}/refresh", headers=H(uid)).json()["inserted"] == 0  # idempotent refresh
    assert client.post(f"/accounts/{acct}/disconnect", headers=H(uid)).status_code == 200
    d = client.get("/dashboard", headers=H(uid)).json()  # data survives disconnect
    assert d["account"]["status"] == "DISCONNECTED" and float(d["cycle"]["expenses"]) == 42500
    assert client.post(f"/accounts/{acct}/refresh", headers=H(uid)).status_code == 409


def test_consent_can_be_rejected_and_aa_sandbox_is_inactive_without_credentials(client, conn):
    uid = make_user(conn)
    conn.commit()
    c = client.post("/consents", headers=H(uid), json={"provider": "demo_bank"}).json()
    assert client.post(f"/consents/{c['consent_id']}/decision", headers=H(uid), json={"decision": "reject"}).json()["status"] == "REJECTED"
    assert client.get("/dashboard", headers=H(uid)).json()["account"] is None  # nothing was fetched
    r = client.post("/consents", headers=H(uid), json={"provider": "aa_sandbox"})
    assert r.status_code == 503 and "not configured" in r.json()["detail"]


def test_chat_without_llm_key_fails_gracefully_and_keeps_the_question(client):
    r = client.post("/chat", headers=H(), json={"message": "How much have I spent this month?"})
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"] and "financial data is safe" in r.json()["detail"]
    convs = client.get("/chat/conversations", headers=H()).json()["conversations"]
    assert convs  # the conversation and the user's message were saved
    msgs = client.get(f"/chat/conversations/{convs[0]['id']}", headers=H()).json()["messages"]
    assert msgs[0]["content"] == "How much have I spent this month?"


def test_chat_conversations_are_private(client, conn):
    client.post("/chat", headers=H(), json={"message": "hello"})
    conv = client.get("/chat/conversations", headers=H()).json()["conversations"][0]["id"]
    other = make_user(conn)
    conn.commit()
    assert client.get(f"/chat/conversations/{conv}", headers=H(other)).status_code == 404
    assert client.post("/chat", headers=H(other), json={"message": "x", "conversation_id": conv}).status_code == 404


def test_alerts_can_be_marked_read_only_by_their_owner(client, conn):
    client.get("/dashboard", headers=H())
    alerts = client.get("/alerts", headers=H()).json()["alerts"]
    assert alerts
    other = make_user(conn)
    conn.commit()
    assert client.post(f"/alerts/{alerts[0]['id']}/read", headers=H(other)).status_code == 404
    assert client.post(f"/alerts/{alerts[0]['id']}/read", headers=H()).status_code == 200


def test_budget_flow(client):
    assert client.put("/budgets", headers=H(), json={"category": "Groceries?", "amount": 100}).status_code == 422
    b = client.put("/budgets", headers=H(), json={"category": "Food", "amount": 5000}).json()
    status = client.get("/budgets", headers=H()).json()["budgets"]
    food = next(x for x in status if x["category"] == "Food")
    assert float(food["amount"]) == 5000 and food["percent_used"] > 100
    assert client.delete(f"/budgets/{b['id']}", headers=H()).status_code == 200


@pytest.mark.parametrize("kind,status,fragment", [
    ("rate_limit", 429, "quota"),
    ("not_configured", 503, "GEMINI_API_KEY"),
    ("model_not_found", 503, "GEMINI_MODEL"),
    ("auth", 503, "rejected"),
    ("unavailable", 503, "temporarily unavailable"),
])
def test_chat_reports_why_the_ai_is_unavailable(client, monkeypatch, kind, status, fragment):
    from app.agent.llm import LLMUnavailable
    import app.api.routes as routes

    def boom(*a, **k):
        raise LLMUnavailable("x", kind=kind)

    monkeypatch.setattr(routes, "run_agent", boom)
    r = client.post("/chat", headers=H(), json={"message": "hi"})
    assert r.status_code == status and fragment in r.json()["detail"] and "financial data is safe" in r.json()["detail"]
