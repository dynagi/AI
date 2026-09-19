"""Agent tool layer + LangGraph loop, against real PostgreSQL. No real LLM is used: a scripted model
decides which tools to call so the tests are deterministic and prove the data path, not model behaviour."""

import json
from contextlib import nullcontext
from decimal import Decimal
from typing import Any, List, Optional

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent.graph import run_agent
from app.agent.tools import ToolContext, build_tools
from app.services.demo_service import simulate_transaction
from app.services.cycle_state import set_target
from app.services.dashboard import build_dashboard
from tests.conftest import DEMO_ACCOUNT, DEMO_USER, make_user

D = Decimal

EXPECTED_TOOLS = {
    "get_current_balance", "get_current_cycle", "get_current_cycle_summary", "get_transaction_history",
    "get_transactions_between_dates", "get_monthly_summary", "compare_cycles", "compare_categories",
    "get_recurring_payments", "get_budget_status", "get_savings_target", "get_savings_progress",
    "get_recent_large_transactions", "get_unusual_transactions", "get_previous_cycle_total",
    "get_remaining_before_previous_cycle", "get_upcoming_obligations",
}


class ScriptedLLM(BaseChatModel):
    """Round 1: call the requested tools. Round 2: answer using ONLY what the tools returned."""

    tool_plan: List[str]
    answer_key: str = ""

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager: Any = None, **kw) -> ChatResult:
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        if not tool_msgs:
            calls = [{"name": n, "args": {}, "id": f"call_{i}", "type": "tool_call"} for i, n in enumerate(self.tool_plan)]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=calls))])
        data = [json.loads(m.content) for m in tool_msgs]
        text = json.dumps({"tools_seen": [m.name for m in tool_msgs], self.answer_key: data[0].get(self.answer_key)})
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


def ctx_for(conn, user_id=DEMO_USER, account_id=None):
    return ToolContext(user_id=user_id, connect=lambda: nullcontext(conn), account_id=account_id)


def tool(conn, name, user_id=DEMO_USER, **args):
    t = next(t for t in build_tools(ctx_for(conn, user_id)) if t.name == name)
    return t.invoke(args)


def demo_new_cycle(conn):
    simulate_transaction(conn, user_id=DEMO_USER, account_id=DEMO_ACCOUNT, transaction_type="SALARY", amount=D("100000"))
    simulate_transaction(conn, user_id=DEMO_USER, account_id=DEMO_ACCOUNT, transaction_type="EXPENSE", amount=D("160"))
    simulate_transaction(conn, user_id=DEMO_USER, account_id=DEMO_ACCOUNT, transaction_type="TRANSFER_IN", amount=D("1000"))


def test_all_seventeen_tools_exist(conn):
    assert {t.name for t in build_tools(ctx_for(conn))} == EXPECTED_TOOLS


def test_tool_results_match_the_database(conn):
    demo_new_cycle(conn)
    bal = tool(conn, "get_current_balance")
    assert bal["current_balance"] == "135840.00" and bal["current_balance_inr"] == "₹1,35,840"
    cyc = tool(conn, "get_current_cycle_summary")
    assert cyc["expenses"] == "160.00" and cyc["income"] == "100000.00" and cyc["other_inflows"] == "1000.00"
    prev = tool(conn, "get_previous_cycle_total")
    assert prev["expenses"] == "42500.00"
    rem = tool(conn, "get_remaining_before_previous_cycle")
    assert rem["remaining"] == "42340.00" and "₹42,340" in rem["message"]
    assert tool(conn, "get_savings_target")["target_set"] is False  # never invented
    assert tool(conn, "get_savings_progress")["status"] == "NO_TARGET"


def test_savings_tools_after_the_user_sets_a_target(conn):
    demo_new_cycle(conn)
    cid = build_dashboard(conn, DEMO_USER)["cycle"]["id"]
    set_target(conn, DEMO_USER, cid, D("25000"))
    p = tool(conn, "get_savings_progress")
    assert p["status"] == "ON_TRACK" and p["planned_spend_limit"] == "75000.00" and p["remaining_spend_capacity"] == "74840.00"


def test_compare_and_category_tools(conn):
    demo_new_cycle(conn)
    cmp = tool(conn, "compare_cycles")
    assert cmp["a"]["expenses"] == "42500.00" and cmp["b"]["expenses"] == "160.00" and cmp["expense_difference"] == "-42340.00"
    cats = tool(conn, "compare_categories")["changes"]
    assert cats and all("category" in c for c in cats)


def test_recurring_only_lists_real_payments(conn):
    r = tool(conn, "get_recurring_payments")
    merchants = {p["merchant"] for p in r["payments"]}
    assert {"Netflix", "Spotify", "Landlord - Sharma Properties"} <= merchants
    assert not any("insurance" in m.lower() or "lic" == m.lower() for m in merchants)


def test_empty_user_gets_an_explicit_no_data_answer(conn):
    uid = make_user(conn)
    assert tool(conn, "get_current_balance", user_id=uid)["error"] == "no_account"
    assert tool(conn, "get_current_cycle_summary", user_id=uid)["error"] == "no_account"


def test_a_user_can_never_read_another_users_data_through_tools(conn):
    other = make_user(conn)
    from app.services.accounts import create_manual_account

    create_manual_account(conn, other, "Other", D("10"))  # other user has an account but no transactions
    hist = tool(conn, "get_transaction_history", user_id=other, cycle="all")
    assert hist["count"] == 0  # not the demo user's 236 rows
    assert tool(conn, "get_current_balance", user_id=other)["current_balance"] == "10.00"
    # passing the demo user's cycle id as a cycle reference is rejected, not honoured
    demo_cycle = build_dashboard(conn, DEMO_USER)["cycle"]["id"]
    res = tool(conn, "get_transaction_history", user_id=other, cycle=demo_cycle)
    assert res.get("error") == "no_cycle"
    res = tool(conn, "compare_cycles", user_id=other, cycle_a=demo_cycle, cycle_b=demo_cycle)
    assert "error" in res and "42500" not in json.dumps(res)


def test_graph_calls_tools_and_answer_is_grounded_in_the_tool_result(conn):
    demo_new_cycle(conn)
    llm = ScriptedLLM(tool_plan=["get_current_cycle_summary"], answer_key="expenses_inr")
    res = run_agent(ctx_for(conn), [], "How much have I spent this month?", llm=llm)
    assert [c["tool"] for c in res.tool_calls] == ["get_current_cycle_summary"]
    answer = json.loads(res.reply)
    assert answer["expenses_inr"] == "₹160"  # from the database, not from the model


def test_graph_supports_multi_tool_questions(conn):
    demo_new_cycle(conn)
    llm = ScriptedLLM(tool_plan=["get_current_cycle_summary", "compare_cycles", "compare_categories", "get_recent_large_transactions"], answer_key="expenses")
    res = run_agent(ctx_for(conn), [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}], "Why did my expenses change?", llm=llm)
    assert [c["tool"] for c in res.tool_calls] == ["get_current_cycle_summary", "compare_cycles", "compare_categories", "get_recent_large_transactions"]
