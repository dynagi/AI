"""Deterministic-first transaction categorization.

Precedence:
  1. a correction this user made earlier for the same merchant (category_rules)
  2. merchant / keyword rules
  3. the category hint supplied by the data source
  4. an LLM, only when everything above is inconclusive (optional, capped)
  5. "Other"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import psycopg

CATEGORIES = [
    "Food", "Shopping", "Transport", "Housing", "Utilities", "Healthcare", "Entertainment",
    "Education", "Travel", "Subscriptions", "Insurance", "EMI/Loans", "Personal Care",
    "Salary", "Investment", "Transfer", "Other",
]

# (pattern, category, subcategory)
RULES: list[tuple[re.Pattern, str, Optional[str]]] = [
    (re.compile(p, re.I), c, s)
    for p, c, s in [
        (r"netflix|spotify|youtube premium|prime video|hotstar|disney", "Subscriptions", "Streaming"),
        (r"rent payment|landlord|house rent|\brent\b", "Housing", "Rent"),
        (r"cult\.?fit|\bgym\b|fitness", "Healthcare", "Fitness"),
        (r"broadband|fibernet|jio ?fiber|xstream|wifi", "Utilities", "Internet"),
        (r"airtel|jio prepaid|vodafone|postpaid|mobile recharge", "Utilities", "Mobile"),
        (r"bescom|electricity|power bill|discom|tata power", "Utilities", "Electricity"),
        (r"\blic\b|insurance|policybazaar|hdfc life|max life", "Insurance", None),
        (r"\bemi\b|bajaj finserv|loan|moneyview", "EMI/Loans", None),
        (r"bigbasket|zepto|blinkit|dmart|grofers|grocery|instamart", "Food", "Groceries"),
        (r"swiggy|zomato|starbucks|chai point|mcdonald|domino|kfc|restaurant|cafe|coffee", "Food", "Dining & Delivery"),
        (r"amazon|myntra|flipkart|ajio|nykaa|croma|electronics", "Shopping", None),
        (r"\buber\b|\bola\b|rapido|indianoil|fuel|petrol|metro card|irctc", "Transport", None),
        (r"bookmyshow|\bpvr\b|cinema|steam|inox", "Entertainment", None),
        (r"apollo|pharmacy|diagnostics|hospital|clinic|medplus", "Healthcare", None),
        (r"udemy|coursera|byju|tuition|school fee|college fee", "Education", None),
        (r"makemytrip|goibibo|indigo|airlines|\boyo\b|airbnb", "Travel", None),
        (r"salon|\bspa\b|personal care", "Personal Care", None),
        (r"own savings|self transfer|sweep", "Transfer", "Own account"),
        (r"mutual fund|\bsip\b|zerodha|groww|upstox|\bnps\b", "Investment", None),
    ]
]


def merchant_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


@dataclass
class Categorization:
    category: str
    subcategory: Optional[str]
    confidence: float
    method: str  # user_correction | rule | type | hint | llm | fallback


class Categorizer:
    def __init__(self, conn: psycopg.Connection, user_id: str, llm_budget: int = 20):
        self.conn = conn
        self.user_id = user_id
        self.llm_budget = llm_budget
        self._rules_cache: Optional[dict[str, tuple[str, Optional[str]]]] = None

    def _user_rules(self) -> dict[str, tuple[str, Optional[str]]]:
        if self._rules_cache is None:
            rows = self.conn.execute(
                "select merchant_key, category, subcategory from category_rules where user_id = %s",
                (self.user_id,),
            ).fetchall()
            self._rules_cache = {r["merchant_key"]: (r["category"], r["subcategory"]) for r in rows}
        return self._rules_cache

    def categorize(
        self,
        description: str,
        merchant: Optional[str],
        transaction_type: str,
        hint: Optional[str] = None,
        hint_sub: Optional[str] = None,
    ) -> Categorization:
        key = merchant_key(merchant or description)
        user = self._user_rules().get(key)
        if user:
            return Categorization(user[0], user[1], 1.0, "user_correction")

        if transaction_type == "SALARY":
            return Categorization("Salary", None, 0.99, "type")

        haystack = f"{merchant or ''} {description}"
        for pattern, category, sub in RULES:
            if pattern.search(haystack):
                return Categorization(category, sub, 0.9, "rule")

        if transaction_type in ("TRANSFER_IN", "TRANSFER_OUT"):
            return Categorization("Transfer", None, 0.9, "type")

        if hint and hint in CATEGORIES:
            return Categorization(hint, hint_sub, 0.7, "hint")

        if transaction_type in ("EXPENSE", "OTHER", "REFUND") and self.llm_budget > 0:
            guess = self._llm_guess(description, merchant)
            if guess:
                return Categorization(guess, None, 0.6, "llm")

        return Categorization("Other", None, 0.3, "fallback")

    def _llm_guess(self, description: str, merchant: Optional[str]) -> Optional[str]:
        from app.agent.llm import get_llm_or_none  # local import: keeps the ledger free of LLM deps

        llm = get_llm_or_none()
        if llm is None:
            return None
        self.llm_budget -= 1
        try:
            reply = llm.invoke(
                f"Classify this bank transaction into exactly one category from: {', '.join(CATEGORIES)}.\n"
                f"Merchant: {merchant or 'unknown'}\nDescription: {description}\n"
                "Answer with only the category name."
            )
            text = (reply.content if isinstance(reply.content, str) else str(reply.content)).strip()
            for c in CATEGORIES:
                if c.lower() == text.lower():
                    return c
        except Exception:
            return None
        return None


def save_correction(
    conn: psycopg.Connection, user_id: str, merchant: str, category: str, subcategory: Optional[str] = None
) -> None:
    conn.execute(
        """
        insert into category_rules (user_id, merchant_key, category, subcategory)
        values (%s, %s, %s, %s)
        on conflict (user_id, merchant_key)
        do update set category = excluded.category, subcategory = excluded.subcategory
        """,
        (user_id, merchant_key(merchant), category, subcategory),
    )
