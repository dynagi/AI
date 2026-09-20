"""HTTP API. Every route takes its user from the verified JWT (Ctx.user_id); no route accepts a user id."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.agent.graph import run_agent
from app.agent.llm import LLMUnavailable
from app.agent.tools import ToolContext
from app.config import get_settings
from app.db import transaction
from app.deps import Ctx, RateLimit, get_ctx
from app.ledger import TRANSACTION_TYPES
from app.providers.aa_sandbox import AASandboxNotConfigured
from app.providers.csv_provider import parse_csv
from app.providers.manual import ManualProvider
from app.services import accounts as accounts_svc
from app.services import analytics as analytics_svc
from app.services import budgets as budgets_svc
from app.services import goals as goals_svc
from app.services import summaries as summaries_svc
from app.services import queries
from app.services.alerts import evaluate_alerts, list_alerts
from app.services.categorization import CATEGORIES, save_correction
from app.services.comparison import compare_cycles, cycle_summary
from app.services.cycle_state import get_target, savings_progress_for, set_target
from app.services.cashflow_risk import check_upcoming_financial_risk
from app.services.dashboard import build_dashboard, upcoming_obligations
from app.services.engagement import build_briefing, clean_tone, simulate_purchase
from app.services.demo_service import ensure_analytics, reset_simulated, setup_cashflow_scenario, simulate_transaction
from app.services.insights import list_insights, refresh_insights
from app.services.ingest import ingest, touch_data_source
from app.services.ledger_service import AccountNotActive, AccountNotFound
from app.services.recurring import list_recurring

router = APIRouter()
MAX_CSV_BYTES = 2_000_000
Money = Decimal


def _account(ctx: Ctx, account_id: Optional[str], create_if_missing: bool = False) -> dict:
    """Account for READS (falls back to a disconnected account so data stays visible), or for WRITES when
    create_if_missing: the active account, creating a manual one if the user has none."""
    if create_if_missing:
        acct = queries.writable_account(ctx.conn, ctx.user_id, account_id)
        if acct is None and not account_id:
            acct = accounts_svc.create_manual_account(ctx.conn, ctx.user_id, "Manual Account", Decimal("0"))
    else:
        acct = queries.primary_account(ctx.conn, ctx.user_id, account_id)
    if acct is None:
        raise HTTPException(404, "No account found. Connect the Demo Bank or add a manual account first.")
    return acct


def _cycle_ref(ctx: Ctx, account: dict, ref: Optional[str]) -> Optional[dict]:
    active = queries.active_cycle(ctx.conn, ctx.user_id, str(account["id"]))
    if ref in (None, "", "current"):
        return active
    if ref == "previous":
        return queries.previous_cycle(ctx.conn, ctx.user_id, active) if active else None
    return queries.get_cycle(ctx.conn, ctx.user_id, ref)


# ---------------------------------------------------------------- basics

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/me")
def me(ctx: Ctx = Depends(get_ctx)):
    row = ctx.conn.execute("select id, email, display_name from users where id = %s", (ctx.user_id,)).fetchone()
    return {**row, "demo_mode": get_settings().demo_mode, "timezone": get_settings().app_timezone}


# ------------------------------------------------------ accounts & sources

@router.get("/accounts")
def get_accounts(ctx: Ctx = Depends(get_ctx)):
    from app.providers.aa_sandbox import AASandboxProvider

    return {
        "accounts": queries.list_accounts(ctx.conn, ctx.user_id),
        "data_sources": ctx.conn.execute(
            "select * from data_sources where user_id = %s order by created_at", (ctx.user_id,)
        ).fetchall(),
        "aa_sandbox_configured": AASandboxProvider.is_configured(),
    }


class ManualAccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    opening_balance: Money = Field(default=Decimal("0"), ge=0, le=Decimal("1e12"))


@router.post("/accounts")
def add_account(body: ManualAccountIn, ctx: Ctx = Depends(get_ctx)):
    return accounts_svc.create_manual_account(ctx.conn, ctx.user_id, body.name.strip(), body.opening_balance)


@router.post("/accounts/{account_id}/disconnect")
def disconnect(account_id: str, ctx: Ctx = Depends(get_ctx)):
    try:
        accounts_svc.disconnect_account(ctx.conn, ctx.user_id, account_id)
    except AccountNotFound:
        raise HTTPException(404, "Account not found.")
    return {"status": "DISCONNECTED", "message": "Disconnected. Your existing financial data is still available."}


@router.post("/accounts/{account_id}/refresh")
def refresh(account_id: str, ctx: Ctx = Depends(get_ctx)):
    try:
        s = accounts_svc.refresh_account(ctx.conn, ctx.user_id, account_id)
    except accounts_svc.ConsentError as exc:
        raise HTTPException(409, str(exc))
    except AASandboxNotConfigured as exc:
        raise HTTPException(503, str(exc))
    except Exception:
        raise HTTPException(502, "Your bank connection could not be refreshed. Your existing financial data is still available.")
    return {"inserted": s.inserted, "duplicates": s.duplicates}


class ConsentIn(BaseModel):
    provider: Literal["demo_bank", "aa_sandbox"] = "demo_bank"


@router.post("/consents")
def create_consent(body: ConsentIn, ctx: Ctx = Depends(get_ctx)):
    try:
        return accounts_svc.request_consent(ctx.conn, ctx.user_id, body.provider)
    except accounts_svc.ConsentError as exc:
        raise HTTPException(409, str(exc))
    except AASandboxNotConfigured as exc:
        raise HTTPException(503, str(exc))


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]


@router.post("/consents/{consent_id}/decision")
def decide(consent_id: str, body: DecisionIn, ctx: Ctx = Depends(get_ctx)):
    try:
        return accounts_svc.decide_consent(ctx.conn, ctx.user_id, consent_id, body.decision == "approve")
    except accounts_svc.ConsentError as exc:
        raise HTTPException(409, str(exc))
    except AASandboxNotConfigured as exc:
        raise HTTPException(503, str(exc))
    except Exception:
        raise HTTPException(502, "The bank / Account Aggregator is unavailable right now. Please try again shortly.")


# ------------------------------------------------------------ dashboard

@router.get("/dashboard")
def dashboard(account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    acct = queries.primary_account(ctx.conn, ctx.user_id, account_id)
    if acct is not None:
        ensure_analytics(ctx.conn, ctx.user_id, str(acct["id"]))
    return build_dashboard(ctx.conn, ctx.user_id, account_id)


# --------------------------------------------------------- transactions

@router.get("/transactions")
def transactions(
    account_id: Optional[str] = None, cycle_id: Optional[str] = None, category: Optional[str] = None,
    q: Optional[str] = None, limit: int = 100, offset: int = 0, ctx: Ctx = Depends(get_ctx),
):
    rows = queries.list_transactions(
        ctx.conn, ctx.user_id, account_id=account_id, cycle_id=cycle_id, category=category, query=q, limit=limit, offset=offset
    )
    return {"transactions": rows, "categories": CATEGORIES}


class TransactionIn(BaseModel):
    transaction_type: str
    amount: Money = Field(gt=0, le=Decimal("1e10"))
    merchant: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = None
    timestamp: Optional[datetime] = None
    account_id: Optional[str] = None


@router.post("/transactions")
def add_transaction(body: TransactionIn, ctx: Ctx = Depends(get_ctx)):
    ttype = body.transaction_type.upper()
    if ttype not in TRANSACTION_TYPES:
        raise HTTPException(422, f"transaction_type must be one of {sorted(TRANSACTION_TYPES)}")
    if body.category and body.category not in CATEGORIES:
        raise HTTPException(422, "Unknown category.")
    acct = _account(ctx, body.account_id, create_if_missing=True)
    ts = body.timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ZoneInfo(get_settings().app_timezone))
    raw = ManualProvider.build(transaction_type=ttype, amount=body.amount, timestamp=ts, merchant=body.merchant,
                               description=body.description, category=body.category)
    try:
        s = ingest(ctx.conn, user_id=ctx.user_id, account_id=str(acct["id"]), raws=[raw], source="manual")
    except AccountNotActive:
        raise HTTPException(409, "This account is disconnected.")
    if s.malformed:
        raise HTTPException(422, s.errors[0])
    touch_data_source(ctx.conn, ctx.user_id, str(acct["id"]), "manual", "Manual Transactions", s.inserted)
    row = ctx.conn.execute(
        """select id, "timestamp", description, merchant, amount, signed_amount, transaction_type, category,
                  balance_after, financial_cycle_id from transactions where id = %s and user_id = %s""",
        (s.inserted_transactions[0].id, ctx.user_id),
    ).fetchone()
    return {"transaction": row, "balance": s.balance, "new_cycle_started": s.new_cycle_started,
            "alerts": [{"type": a["alert_type"], "title": a["title"], "message": a["message"]} for a in s.alerts]}


@router.post("/transactions/csv", dependencies=[Depends(RateLimit(10, 60))])
async def import_csv(file: UploadFile = File(...), account_id: Optional[str] = Form(None), ctx: Ctx = Depends(get_ctx)):
    data = await file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        raise HTTPException(413, "That CSV is too large (limit 2 MB).")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "This file is not a valid UTF-8 CSV.")
    raws, errors = parse_csv(text)
    if not raws:
        raise HTTPException(400, " ".join(errors[:3]) or "No transactions found in this CSV.")
    acct = _account(ctx, account_id, create_if_missing=True)
    s = ingest(ctx.conn, user_id=ctx.user_id, account_id=str(acct["id"]), raws=raws, source="csv")
    touch_data_source(ctx.conn, ctx.user_id, str(acct["id"]), "csv", "CSV Import", s.inserted)
    return {"inserted": s.inserted, "duplicates": s.duplicates, "malformed": s.malformed + len(errors),
            "errors": (errors + s.errors)[:20], "balance": s.balance}


class CategoryIn(BaseModel):
    category: str
    subcategory: Optional[str] = Field(default=None, max_length=50)


@router.patch("/transactions/{transaction_id}/category")
def correct_category(transaction_id: str, body: CategoryIn, ctx: Ctx = Depends(get_ctx)):
    if body.category not in CATEGORIES:
        raise HTTPException(422, "Unknown category.")
    row = ctx.conn.execute(
        """update transactions set category = %s, subcategory = %s
           where id = %s and user_id = %s returning id, account_id, merchant, description""",
        (body.category, body.subcategory, transaction_id, ctx.user_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Transaction not found.")
    save_correction(ctx.conn, ctx.user_id, row["merchant"] or row["description"], body.category, body.subcategory)
    refresh_insights(ctx.conn, ctx.user_id, str(row["account_id"]))
    return {"status": "ok"}


# --------------------------------------------------- cycles & comparisons

@router.get("/cycles")
def cycles(account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    acct = queries.primary_account(ctx.conn, ctx.user_id, account_id)
    if acct is None:
        return {"cycles": []}
    rows = queries.list_cycles(ctx.conn, ctx.user_id, str(acct["id"]))
    return {"cycles": [cycle_summary(ctx.conn, ctx.user_id, c) for c in rows]}


@router.get("/cycles/{cycle_id}")
def cycle_detail(cycle_id: str, ctx: Ctx = Depends(get_ctx)):
    c = queries.get_cycle(ctx.conn, ctx.user_id, cycle_id)
    if c is None:
        raise HTTPException(404, "Cycle not found.")
    return cycle_summary(ctx.conn, ctx.user_id, c)


@router.get("/comparisons")
def comparisons(a: Optional[str] = "previous", b: Optional[str] = "current", account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    acct = _account(ctx, account_id)
    ca, cb = _cycle_ref(ctx, acct, a), _cycle_ref(ctx, acct, b)
    cycles_list = [
        {"id": str(c["id"]), "label": cycle_summary(ctx.conn, ctx.user_id, c)["label"], "status": c["status"]}
        for c in queries.list_cycles(ctx.conn, ctx.user_id, str(acct["id"]))
    ]
    if ca is None or cb is None:
        return {"cycles": cycles_list, "comparison": None,
                "message": "There is no previous cycle to compare with yet." if a == "previous" else "Cycle not found."}
    goals = [{"name": g["name"], "progress_percent": g["progress_percent"], "current_amount": g["current_amount"], "target_amount": g["target_amount"]}
             for g in goals_svc.goals_overview(ctx.conn, ctx.user_id, str(acct["id"]))["goals"]]
    return {"cycles": cycles_list, "comparison": compare_cycles(ctx.conn, ctx.user_id, ca, cb), "goals": goals}


# ------------------------------------------------------ savings & budgets

@router.get("/savings")
def savings(account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    acct = _account(ctx, account_id)
    cyc = queries.active_cycle(ctx.conn, ctx.user_id, str(acct["id"]))
    if cyc is None:
        return {"current": None, "history": []}
    progress = savings_progress_for(ctx.conn, ctx.user_id, cyc)
    history = []
    for c in queries.list_cycles(ctx.conn, ctx.user_id, str(acct["id"])):
        if c["status"] == "ACTIVE":
            continue
        s = cycle_summary(ctx.conn, ctx.user_id, c)
        target = get_target(ctx.conn, ctx.user_id, str(c["id"]))
        history.append({"cycle_id": s["id"], "label": s["label"], "income": s["income"], "expenses": s["expenses"],
                        "savings": s["savings"], "target": target, "met": (s["savings"] >= target) if target is not None else None})
    return {"current": {**progress.as_dict(), "cycle_id": str(cyc["id"]), "cycle": cycle_summary(ctx.conn, ctx.user_id, cyc)["label"]},
            "history": history}


class TargetIn(BaseModel):
    target_amount: Money = Field(ge=0, le=Decimal("1e10"))
    cycle_id: Optional[str] = None


@router.put("/savings/target")
def put_target(body: TargetIn, account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    acct = _account(ctx, account_id)
    cyc = queries.get_cycle(ctx.conn, ctx.user_id, body.cycle_id) if body.cycle_id else queries.active_cycle(ctx.conn, ctx.user_id, str(acct["id"]))
    if cyc is None:
        raise HTTPException(404, "There is no active financial cycle to set a target for yet.")
    set_target(ctx.conn, ctx.user_id, str(cyc["id"]), body.target_amount)
    ctx.conn.execute(
        "update agent_alerts set is_read = true where user_id = %s and dedupe_key = %s", (ctx.user_id, f"set_target:{cyc['id']}")
    )
    if cyc["status"] == "ACTIVE":
        evaluate_alerts(ctx.conn, ctx.user_id, str(cyc["account_id"]), inserted=[], new_cycle_ids=[])
    progress = savings_progress_for(ctx.conn, ctx.user_id, queries.get_cycle(ctx.conn, ctx.user_id, str(cyc["id"])))
    return progress.as_dict()


@router.get("/budgets")
def get_budgets(account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    acct = queries.primary_account(ctx.conn, ctx.user_id, account_id)
    if acct is None:
        return {"budgets": [], "totals": None, "commitments": None, "categories": CATEGORIES}
    return {**budgets_svc.budget_overview(ctx.conn, ctx.user_id, str(acct["id"])), "categories": CATEGORIES}


class BudgetIn(BaseModel):
    category: str
    amount: Money = Field(gt=0, le=Decimal("1e10"))


@router.put("/budgets")
def put_budget(body: BudgetIn, ctx: Ctx = Depends(get_ctx)):
    if body.category not in CATEGORIES:
        raise HTTPException(422, "Unknown category.")
    row = budgets_svc.set_budget(ctx.conn, ctx.user_id, body.category, body.amount)
    acct = queries.primary_account(ctx.conn, ctx.user_id)
    if acct:
        evaluate_alerts(ctx.conn, ctx.user_id, str(acct["id"]), inserted=[], new_cycle_ids=[])
    return row


@router.delete("/budgets/{budget_id}")
def del_budget(budget_id: str, ctx: Ctx = Depends(get_ctx)):
    if not budgets_svc.delete_budget(ctx.conn, ctx.user_id, budget_id):
        raise HTTPException(404, "Budget not found.")
    return {"status": "deleted"}


# ------------------------------------------- recurring, insights, alerts

@router.get("/recurring")
def recurring(ctx: Ctx = Depends(get_ctx)):
    acct = queries.primary_account(ctx.conn, ctx.user_id)
    return {"payments": list_recurring(ctx.conn, ctx.user_id),
            "upcoming": upcoming_obligations(ctx.conn, ctx.user_id, str(acct["id"])) if acct else None}


@router.get("/cashflow-risk")
def cashflow_risk(account_id: Optional[str] = None, days: int = Query(30, ge=1, le=90), ctx: Ctx = Depends(get_ctx)):
    """Read-only warning about upcoming recurring payments vs balance, expected income, savings and budget."""
    acct = _account(ctx, account_id)
    return check_upcoming_financial_risk(ctx.conn, ctx.user_id, str(acct["id"]), horizon_days=days)


class WhatIfIn(BaseModel):
    amount: Money = Field(gt=0, le=Decimal("1e10"))
    label: str = Field(default="Purchase", max_length=60)
    days: int = Field(default=0, ge=0, le=90)
    account_id: Optional[str] = None


@router.post("/whatif", dependencies=[Depends(RateLimit(60, 60))])
def whatif(body: WhatIfIn, ctx: Ctx = Depends(get_ctx)):
    """Hypothetical purchase: shows how it would change the cash-flow warning. Nothing is saved."""
    acct = _account(ctx, body.account_id)
    return simulate_purchase(ctx.conn, ctx.user_id, str(acct["id"]), body.amount, body.label, body.days)


@router.get("/briefing")
def briefing(tone: Optional[str] = None, account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    acct = _account(ctx, account_id)
    return build_briefing(ctx.conn, ctx.user_id, str(acct["id"]), tone)


@router.get("/insights")
def insights(ctx: Ctx = Depends(get_ctx)):
    return {"insights": list_insights(ctx.conn, ctx.user_id)}


@router.get("/alerts")
def alerts(unread_only: bool = False, ctx: Ctx = Depends(get_ctx)):
    return {"alerts": list_alerts(ctx.conn, ctx.user_id, unread_only=unread_only)}


@router.post("/alerts/read-all")
def read_all(ctx: Ctx = Depends(get_ctx)):
    ctx.conn.execute("update agent_alerts set is_read = true where user_id = %s", (ctx.user_id,))
    return {"status": "ok"}


@router.post("/alerts/{alert_id}/read")
def read_alert(alert_id: str, ctx: Ctx = Depends(get_ctx)):
    n = ctx.conn.execute("update agent_alerts set is_read = true where id = %s and user_id = %s", (alert_id, ctx.user_id)).rowcount
    if not n:
        raise HTTPException(404, "Alert not found.")
    return {"status": "ok"}


# ------------------------------------------------------------- chat

_SAFE = " Your financial data is safe and unaffected."
_LLM_MESSAGES = {
    "not_configured": (503, "The AI assistant is not configured: add GEMINI_API_KEY to backend/.env and restart the backend." + _SAFE),
    "rate_limit": (429, "The AI provider's usage quota has been reached. Wait a minute and try again, or set GEMINI_MODEL / GEMINI_API_KEY in backend/.env to a model or key with quota." + _SAFE),
    "model_not_found": (503, "The configured AI model is not available. Set GEMINI_MODEL=gemini-flash-latest in backend/.env." + _SAFE),
    "auth": (503, "The AI provider rejected the API key or request. Check GEMINI_API_KEY in backend/.env." + _SAFE),
    "unavailable": (503, "The AI assistant is temporarily unavailable." + _SAFE),
}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    tone: Optional[str] = None  # chill | coach | roast: wording only
    conversation_id: Optional[str] = None


@router.post("/chat", dependencies=[Depends(RateLimit(20, 60))])
def chat(body: ChatIn, ctx: Ctx = Depends(get_ctx)):
    conn = ctx.conn
    acct = queries.primary_account(conn, ctx.user_id)
    conv_id = body.conversation_id
    if conv_id:
        owned = conn.execute("select id from agent_conversations where id = %s and user_id = %s", (conv_id, ctx.user_id)).fetchone()
        if not owned:
            raise HTTPException(404, "Conversation not found.")
    else:
        conv_id = str(conn.execute(
            "insert into agent_conversations (user_id, title) values (%s, %s) returning id", (ctx.user_id, body.message[:60])
        ).fetchone()["id"])

    history = conn.execute(
        "select role, content from agent_messages where conversation_id = %s and user_id = %s and role in ('user','assistant') order by created_at, id limit 40",
        (conv_id, ctx.user_id),
    ).fetchall()
    conn.execute("insert into agent_messages (conversation_id, user_id, role, content) values (%s, %s, 'user', %s)", (conv_id, ctx.user_id, body.message))

    if acct is None:
        reply, calls = ("I don't have any financial data for you yet. Connect the Demo Bank or add a manual account and some transactions, "
                        "and I can answer from that data."), []
    else:
        # The agent's tools open their own short read-only transactions; release ours first so the user message is saved
        # even if the model call fails.
        conn.commit()

        class _Own:
            def __enter__(self_inner):
                self_inner.cm = transaction()
                return self_inner.cm.__enter__()

            def __exit__(self_inner, *exc):
                return self_inner.cm.__exit__(*exc)

        try:
            res = run_agent(ToolContext(user_id=ctx.user_id, connect=_Own, account_id=str(acct["id"])), history, body.message, tone=clean_tone(body.tone))
        except LLMUnavailable as exc:
            raise HTTPException(*_LLM_MESSAGES.get(exc.kind, _LLM_MESSAGES["unavailable"]))
        reply, calls = res.reply, res.tool_calls

    conn.execute(
        "insert into agent_messages (conversation_id, user_id, role, content, tool_calls) values (%s, %s, 'assistant', %s, %s::jsonb)",
        (conv_id, ctx.user_id, reply, json.dumps(calls) if calls else None),
    )
    conn.execute("update agent_conversations set updated_at = now() where id = %s and user_id = %s", (conv_id, ctx.user_id))
    return {"conversation_id": conv_id, "reply": reply, "tool_calls": [{"tool": c["tool"], "args": c["args"]} for c in calls]}


@router.get("/chat/conversations")
def conversations(ctx: Ctx = Depends(get_ctx)):
    return {"conversations": ctx.conn.execute(
        "select id, title, updated_at from agent_conversations where user_id = %s order by updated_at desc limit 30", (ctx.user_id,)
    ).fetchall()}


@router.get("/chat/conversations/{conversation_id}")
def conversation(conversation_id: str, ctx: Ctx = Depends(get_ctx)):
    conv = ctx.conn.execute("select id, title from agent_conversations where id = %s and user_id = %s", (conversation_id, ctx.user_id)).fetchone()
    if not conv:
        raise HTTPException(404, "Conversation not found.")
    msgs = ctx.conn.execute(
        "select id, role, content, tool_calls, created_at from agent_messages where conversation_id = %s and user_id = %s order by created_at, id",
        (conversation_id, ctx.user_id),
    ).fetchall()
    return {"conversation": conv, "messages": msgs}


# -------------------------------------------------- Demo Bank Simulator

class DemoTxnIn(BaseModel):
    type: str
    amount: Money = Field(gt=0, le=Decimal("1e10"))
    merchant: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = None
    timestamp: Optional[datetime] = None
    account_id: Optional[str] = None


def _require_demo() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(404, "Not found.")


@router.post("/demo/transactions", dependencies=[Depends(RateLimit(60, 60))])
def demo_transaction(body: DemoTxnIn, ctx: Ctx = Depends(get_ctx)):
    _require_demo()
    ttype = body.type.upper()
    if ttype not in TRANSACTION_TYPES:
        raise HTTPException(422, f"type must be one of {sorted(TRANSACTION_TYPES)}")
    acct = _account(ctx, body.account_id)
    try:
        s = simulate_transaction(
            ctx.conn, user_id=ctx.user_id, account_id=str(acct["id"]), transaction_type=ttype, amount=body.amount,
            merchant=body.merchant, description=body.description, timestamp=body.timestamp, category=body.category,
        )
    except AccountNotActive:
        raise HTTPException(409, "This account is disconnected.")
    if s.malformed:
        raise HTTPException(422, s.errors[0])
    t = ctx.conn.execute(
        """select id, "timestamp", description, merchant, amount, signed_amount, transaction_type, category, balance_after
           from transactions where id = %s and user_id = %s""", (s.inserted_transactions[0].id, ctx.user_id),
    ).fetchone()
    return {"transaction": t, "balance": s.balance, "new_cycle_started": s.new_cycle_started,
            "alerts": [{"type": a["alert_type"], "title": a["title"], "message": a["message"]} for a in s.alerts]}


@router.post("/demo/cashflow-scenario")
def demo_cashflow_scenario(account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    """Sets up the cash-flow warning demo: balance Rs 1,000 with a Rs 2,000 subscription due in 5 days."""
    _require_demo()
    acct = _account(ctx, account_id)
    try:
        return setup_cashflow_scenario(ctx.conn, ctx.user_id, str(acct["id"]))
    except AccountNotActive:
        raise HTTPException(409, "This account is disconnected.")


@router.post("/demo/reset")
def demo_reset(account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    """Removes ONLY transactions created by the simulator (metadata.simulated). Seeded and real data stay."""
    _require_demo()
    acct = _account(ctx, account_id)
    return reset_simulated(ctx.conn, ctx.user_id, str(acct["id"]))


# ----------------------------------------------------------- financial goals

class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    goal_type: str = "CUSTOM"
    target_amount: Money = Field(gt=0, le=Decimal("1e10"))
    current_amount: Money = Field(default=Decimal("0"), ge=0, le=Decimal("1e10"))
    target_date: date
    priority: str = "MEDIUM"


class GoalPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    goal_type: Optional[str] = None
    target_amount: Optional[Money] = Field(default=None, gt=0, le=Decimal("1e10"))
    target_date: Optional[date] = None
    priority: Optional[str] = None
    status: Optional[str] = None  # ACTIVE | PAUSED | COMPLETED


class ContributionIn(BaseModel):
    amount: Money = Field(gt=0, le=Decimal("1e10"))
    notes: Optional[str] = Field(default=None, max_length=200)
    timestamp: Optional[datetime] = None


def _goal_errors(fn):
    try:
        return fn()
    except goals_svc.GoalNotFound:
        raise HTTPException(404, "Goal not found.")
    except goals_svc.GoalError as exc:
        raise HTTPException(422, str(exc))


@router.get("/goals")
def list_goals(account_id: Optional[str] = None, ctx: Ctx = Depends(get_ctx)):
    acct = queries.primary_account(ctx.conn, ctx.user_id, account_id)
    ov = goals_svc.goals_overview(ctx.conn, ctx.user_id, str(acct["id"]) if acct else None)
    return {**ov, "goal_types": list(goals_svc.GOAL_TYPES), "priorities": list(goals_svc.PRIORITIES)}


@router.post("/goals")
def create_goal(body: GoalIn, ctx: Ctx = Depends(get_ctx)):
    g = _goal_errors(lambda: goals_svc.create_goal(
        ctx.conn, ctx.user_id, name=body.name, goal_type=body.goal_type, target_amount=body.target_amount,
        current_amount=body.current_amount, target_date=body.target_date, priority=body.priority))
    acct = queries.primary_account(ctx.conn, ctx.user_id)
    if acct:
        evaluate_alerts(ctx.conn, ctx.user_id, str(acct["id"]), inserted=[], new_cycle_ids=[])
    return g


@router.get("/goals/{goal_id}")
def goal_detail(goal_id: str, ctx: Ctx = Depends(get_ctx)):
    _goal_errors(lambda: goals_svc.get_goal(ctx.conn, ctx.user_id, goal_id))
    acct = queries.primary_account(ctx.conn, ctx.user_id)
    ov = goals_svc.goals_overview(ctx.conn, ctx.user_id, str(acct["id"]) if acct else None)
    analysis = next((g for g in ov["goals"] if g["id"] == goal_id), None)
    return {"goal": analysis, "combined": ov["combined"], "contributions": goals_svc.contributions_for(ctx.conn, ctx.user_id, goal_id)}


@router.patch("/goals/{goal_id}")
def edit_goal(goal_id: str, body: GoalPatch, ctx: Ctx = Depends(get_ctx)):
    return _goal_errors(lambda: goals_svc.update_goal(ctx.conn, ctx.user_id, goal_id, body.model_dump(exclude_none=True)))


@router.post("/goals/{goal_id}/contributions")
def contribute(goal_id: str, body: ContributionIn, ctx: Ctx = Depends(get_ctx)):
    contribution, goal = _goal_errors(lambda: goals_svc.add_contribution(
        ctx.conn, ctx.user_id, goal_id, body.amount, body.notes, body.timestamp))
    return {"contribution": contribution, "goal": goal}


# ------------------------------------------------- monthly summaries & actions

class GenerateIn(BaseModel):
    cycle_id: Optional[str] = None  # default: the current (active) cycle


@router.get("/summaries")
def summaries(ctx: Ctx = Depends(get_ctx)):
    acct = queries.primary_account(ctx.conn, ctx.user_id)
    if acct:
        summaries_svc.sync_summaries(ctx.conn, ctx.user_id, str(acct["id"]))
    return {"summaries": summaries_svc.list_summaries(ctx.conn, ctx.user_id), "open_actions": summaries_svc.open_actions(ctx.conn, ctx.user_id)}


@router.post("/summaries/generate", dependencies=[Depends(RateLimit(20, 60))])
def generate(body: GenerateIn, ctx: Ctx = Depends(get_ctx)):
    cycle_id = body.cycle_id
    if not cycle_id:
        acct = _account(ctx, None)
        cyc = queries.active_cycle(ctx.conn, ctx.user_id, str(acct["id"]))
        if cyc is None:
            raise HTTPException(404, "There is no current financial cycle to summarise yet.")
        cycle_id = str(cyc["id"])
    try:
        row = summaries_svc.generate_summary(ctx.conn, ctx.user_id, cycle_id)
    except summaries_svc.SummaryNotFound:
        raise HTTPException(404, "Cycle not found.")
    return summaries_svc.get_summary(ctx.conn, ctx.user_id, str(row["id"]))


@router.get("/summaries/{summary_id}")
def summary_detail(summary_id: str, ctx: Ctx = Depends(get_ctx)):
    try:
        return summaries_svc.get_summary(ctx.conn, ctx.user_id, summary_id)
    except summaries_svc.SummaryNotFound:
        raise HTTPException(404, "Summary not found.")


class ActionStatusIn(BaseModel):
    status: Literal["OPEN", "COMPLETED", "DISMISSED"]


@router.patch("/summary-actions/{action_id}")
def action_status(action_id: str, body: ActionStatusIn, ctx: Ctx = Depends(get_ctx)):
    try:
        return summaries_svc.set_action_status(ctx.conn, ctx.user_id, action_id, body.status)
    except summaries_svc.SummaryNotFound:
        raise HTTPException(404, "Action item not found.")


# ----------------------------------------------------- insights, trends, daily

@router.get("/insights/overview")
def insights_overview(ctx: Ctx = Depends(get_ctx)):
    """Everything the Insights page shows. Each section is computed from the ledger and carries its supporting data."""
    acct = queries.primary_account(ctx.conn, ctx.user_id)
    if acct is None:
        return {"account": None}
    aid = str(acct["id"])
    ensure_analytics(ctx.conn, ctx.user_id, aid)
    cycle = queries.active_cycle(ctx.conn, ctx.user_id, aid)
    ov = goals_svc.goals_overview(ctx.conn, ctx.user_id, aid)
    budgets = budgets_svc.budget_status(ctx.conn, ctx.user_id, aid)
    out = {
        "account": {"id": aid, "name": acct["name"]},
        "trends": analytics_svc.monthly_trends(ctx.conn, ctx.user_id, aid, 6),
        "unusual_activity": analytics_svc.unusual_for_cycle(ctx.conn, ctx.user_id, cycle, aid) if cycle else [],
        "recurring": list_recurring(ctx.conn, ctx.user_id),
        "upcoming_obligations": upcoming_obligations(ctx.conn, ctx.user_id, aid),
        "goal_risks": [g for g in ov["goals"] if g["status"] in ("AT_RISK", "BEHIND")],
        "goals_combined": ov["combined"],
        "budget_risks": [b for b in budgets if b["status"] != "ON_TRACK"],
        "insights": list_insights(ctx.conn, ctx.user_id, limit=20),
        "savings": None,
    }
    if cycle:
        p = savings_progress_for(ctx.conn, ctx.user_id, cycle)
        out["savings"] = {**p.as_dict(), "cycle": cycle_summary(ctx.conn, ctx.user_id, cycle)["label"]}
    return out


@router.get("/trends")
def trends(limit: int = 6, ctx: Ctx = Depends(get_ctx)):
    acct = _account(ctx, None)
    return {"cycles": analytics_svc.monthly_trends(ctx.conn, ctx.user_id, str(acct["id"]), min(max(limit, 2), 12))}


@router.get("/spending/daily")
def spending_daily(days: int = 14, ctx: Ctx = Depends(get_ctx)):
    acct = _account(ctx, None)
    return analytics_svc.daily_spending(ctx.conn, ctx.user_id, str(acct["id"]), min(max(days, 1), 60))
