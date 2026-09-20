"""LangGraph agent: a tool-calling loop over the user's data tools.

    START -> agent (LLM, tools bound) --tool calls?--> tools --> agent ... --> END
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.llm import LLMUnavailable, get_llm
from app.agent.prompts import system_prompt
from app.agent.tools import ToolContext, build_tools
from app.logging_utils import log_event

MAX_STEPS = 14  # graph steps (each tool round trip is 2)


def build_graph(llm: BaseChatModel, tools: list, tone: str = "chill"):
    bound = llm.bind_tools(tools)
    prompt = system_prompt(tone)

    def agent(state: MessagesState) -> dict:
        reply = bound.invoke([SystemMessage(content=prompt)] + state["messages"])
        return {"messages": [reply]}

    g = StateGraph(MessagesState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition)
    g.add_edge("tools", "agent")
    return g.compile()


def _text(msg: BaseMessage) -> str:
    c = msg.content
    if isinstance(c, str):
        return c.strip()
    parts = []
    for p in c:
        if isinstance(p, str):
            parts.append(p)
        elif isinstance(p, dict) and p.get("type") == "text":
            parts.append(p.get("text", ""))
    return "".join(parts).strip()


@dataclass
class ChatResult:
    reply: str
    tool_calls: list[dict]


def run_agent(
    ctx: ToolContext, history: list[dict], message: str, llm: Optional[BaseChatModel] = None, tone: str = "chill"
) -> ChatResult:
    """`history` is prior [{role, content}] turns (user/assistant only)."""
    llm = llm or get_llm()
    tools = build_tools(ctx)
    graph = build_graph(llm, tools, tone)

    msgs: list[BaseMessage] = []
    for h in history[-20:]:
        msgs.append(HumanMessage(content=h["content"]) if h["role"] == "user" else AIMessage(content=h["content"]))
    msgs.append(HumanMessage(content=message))

    try:
        out = graph.invoke({"messages": msgs}, {"recursion_limit": MAX_STEPS})
    except LLMUnavailable:
        raise
    except Exception as exc:
        name = type(exc).__name__
        log_event("agent.error", user_id=ctx.user_id, error=name)
        if name in {"GraphRecursionError"}:
            return ChatResult("I couldn't finish that analysis. Could you ask a narrower question?", [])
        low = name.lower()
        kind = (
            "rate_limit" if "ratelimit" in low or "resourceexhausted" in low or "quota" in str(exc).lower()[:400]
            else "model_not_found" if "notfound" in low
            else "auth" if "auth" in low or "permission" in low or "invalidargument" in low
            else "unavailable"
        )
        raise LLMUnavailable(f"The AI provider failed: {name}", kind=kind) from exc

    new = out["messages"][len(msgs):]
    calls: dict[str, dict] = {}
    for m in new:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls or []:
                calls[tc["id"]] = {"tool": tc["name"], "args": tc["args"], "output": None}
        elif isinstance(m, ToolMessage) and m.tool_call_id in calls:
            raw = m.content if isinstance(m.content, str) else json.dumps(m.content)
            calls[m.tool_call_id]["output"] = raw[:4000]
    final = next((m for m in reversed(new) if isinstance(m, AIMessage) and not m.tool_calls), None)
    reply = _text(final) if final else ""
    if not reply:
        reply = "I wasn't able to produce an answer from your data. Could you rephrase the question?"
    log_event("agent.response", user_id=ctx.user_id, tools=[c["tool"] for c in calls.values()])
    return ChatResult(reply, list(calls.values()))
