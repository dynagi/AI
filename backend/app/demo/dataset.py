"""Deterministic demo history (sandbox data — not real banking data).

One source of truth used by BOTH the SQL seed generator and the Demo Bank
provider, so a seeded demo user and a user who clicks "Connect Demo Bank" end
up with identical data.

Story:
  * The account starts with an opening balance of Rs 35,000.
  * A salary of Rs 1,00,000 lands at 11:27:04 IST on the last day of each month
    (31 Mar ... 31 Aug 2026), each starting a new financial cycle.
  * Each cycle's expenses total a fixed amount (38,200 / 41,500 / 39,800 /
    44,100 / 46,200 / 42,500) so historical comparisons are exact.
  * Shortly before the next salary an automatic sweep moves the surplus to the
    user's own savings account, so the balance returns to Rs 35,000 every time.
    (TRANSFER_OUT is not an expense.) Right before the demo salary the account
    therefore holds exactly Rs 35,000 again.
  * The final seeded cycle (31 Aug -> 30 Sep 11:27:04) is still ACTIVE. Credit
    the September salary from the Demo Bank Simulator to start the next cycle.

There is deliberately NO insurance / EMI / loan spending: FinPilot must never
show categories that have no supporting transactions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.providers.base import RawTransaction

IST = timezone(timedelta(hours=5, minutes=30))

DEMO_OPENING_BALANCE = Decimal("35000")
DEMO_SALARY_AMOUNT = Decimal("100000")
DEMO_SAVINGS_TARGET_TO_SET = Decimal("25000")  # what the demo user is asked to set in the live demo

# Salary landing times (each opens a financial cycle).
SALARY_TIMES = [
    datetime(2026, 3, 31, 11, 27, 4, tzinfo=IST),
    datetime(2026, 4, 30, 11, 27, 4, tzinfo=IST),
    datetime(2026, 5, 31, 11, 27, 4, tzinfo=IST),
    datetime(2026, 6, 30, 11, 27, 4, tzinfo=IST),
    datetime(2026, 7, 31, 11, 27, 4, tzinfo=IST),
    datetime(2026, 8, 31, 11, 27, 4, tzinfo=IST),
]
# The salary the live demo credits next.
DEMO_NEXT_SALARY_TIME = datetime(2026, 9, 30, 11, 27, 4, tzinfo=IST)

# Total EXPENSE per cycle, in the same order as SALARY_TIMES.
CYCLE_EXPENSE_TOTALS = [38200, 41500, 39800, 44100, 46200, 42500]

# Variable (non-recurring) spend per cycle. Food is the balancing category.
# order: shopping, transport, entertainment, healthcare, electricity
VARIABLE_SPEND = [
    (4200, 3100, 1300, 900, 1450),
    (6300, 3400, 1800, 1100, 1520),
    (4800, 3000, 1200, 700, 1610),
    (7900, 3600, 2100, 1600, 1700),
    (9800, 3300, 2600, 1200, 1650),
    (3600, 2900, 900, 7200, 2450),  # latest cycle: one big pharmacy/diagnostics bill + a high electricity bill
]

# Fixed monthly payments: (merchant, description, amount, day offset from salary, hour, minute, category, subcategory)
FIXED_MONTHLY = [
    ("Landlord - Sharma Properties", "RENT PAYMENT NEFT", 15000, 1, 9, 5, "Housing", "Rent"),
    ("Netflix", "NETFLIX.COM SUBSCRIPTION", 649, 3, 6, 40, "Subscriptions", "Streaming"),
    ("Spotify", "SPOTIFY INDIA", 119, 5, 7, 15, "Subscriptions", "Streaming"),
    ("Cult.fit", "CULTFIT MEMBERSHIP", 1499, 7, 8, 30, "Healthcare", "Fitness"),
    ("ACT Fibernet", "ACT BROADBAND BILLPAY", 999, 9, 10, 20, "Utilities", "Internet"),
    ("Airtel", "AIRTEL POSTPAID BILLPAY", 599, 11, 10, 45, "Utilities", "Mobile"),
]
FIXED_TOTAL = sum(item[2] for item in FIXED_MONTHLY)  # 18,865

GROCERY_MERCHANTS = ["BigBasket", "Zepto", "Blinkit", "DMart"]
DELIVERY_MERCHANTS = ["Swiggy", "Zomato", "Starbucks", "McDonald's"]
TRANSPORT_MERCHANTS = ["Uber", "Ola", "Rapido", "IndianOil Fuel"]
SHOPPING_MERCHANTS = ["Amazon", "Myntra", "Flipkart"]
ENTERTAINMENT_MERCHANTS = ["BookMyShow", "PVR Cinemas"]


@dataclass
class _Counter:
    n: int = 0

    def next(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}-{self.n:04d}"


def _split(rng: random.Random, total: int, parts: int) -> list[int]:
    """Split `total` into `parts` positive integers that sum exactly to total."""
    if parts <= 1:
        return [total]
    weights = [rng.uniform(0.55, 1.45) for _ in range(parts)]
    scale = total / sum(weights)
    chunks = [max(1, int(round(w * scale))) for w in weights[:-1]]
    chunks.append(total - sum(chunks))
    assert chunks[-1] > 0, "unlucky split; adjust seed"
    return chunks


def _at(day_start: datetime, offset_days: int, rng: random.Random) -> datetime:
    base = day_start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset_days)
    return base.replace(hour=rng.randint(8, 21), minute=rng.randint(0, 59), second=rng.randint(0, 59))


def generate_demo_history() -> list[RawTransaction]:
    out: list[RawTransaction] = []
    ids = _Counter()

    for idx, salary_at in enumerate(SALARY_TIMES):
        rng = random.Random(f"finpilot-demo-cycle-{idx}")
        next_salary_at = SALARY_TIMES[idx + 1] if idx + 1 < len(SALARY_TIMES) else DEMO_NEXT_SALARY_TIME
        cycle_days = (next_salary_at - salary_at).days  # 30 or 31
        last_spend_offset = cycle_days - 3

        total = CYCLE_EXPENSE_TOTALS[idx]
        shopping, transport, ent, health, elec = VARIABLE_SPEND[idx]
        food = total - FIXED_TOTAL - (shopping + transport + ent + health + elec)
        assert food > 3000, f"cycle {idx}: food balancer too small ({food})"

        cycle: list[RawTransaction] = []

        def add(ts, description, merchant, amount, ttype, category, sub=None):
            cycle.append(
                RawTransaction(
                    timestamp=ts,
                    description=description,
                    merchant=merchant,
                    amount=Decimal(amount),
                    transaction_type=ttype,
                    category=category,
                    subcategory=sub,
                    external_id=ids.next(f"demo-{salary_at:%Y%m%d}"),
                    metadata={"seed": True},
                )
            )

        add(salary_at, "SALARY CREDIT - EMPLOYER PVT LTD", "Employer Pvt Ltd", DEMO_SALARY_AMOUNT, "SALARY", "Salary")

        for merchant, desc, amount, day, hh, mm, cat, sub in FIXED_MONTHLY:
            ts = (salary_at + timedelta(days=day)).replace(hour=hh, minute=mm, second=0)
            add(ts, desc, merchant, amount, "EXPENSE", cat, sub)

        # Electricity: one bill around the 17th day.
        ts = (salary_at + timedelta(days=17)).replace(hour=12, minute=10, second=0)
        add(ts, "BESCOM ELECTRICITY BILLPAY", "BESCOM", elec, "EXPENSE", "Utilities", "Electricity")

        # Food: groceries (5) + delivery/dining (8).
        grocery_total = int(round(food * 0.45))
        for amt in _split(rng, grocery_total, 5):
            m = rng.choice(GROCERY_MERCHANTS)
            add(_at(salary_at, rng.randint(1, last_spend_offset), rng), f"{m.upper()} ORDER", m, amt, "EXPENSE", "Food", "Groceries")
        for amt in _split(rng, food - grocery_total, 8):
            m = rng.choice(DELIVERY_MERCHANTS)
            add(_at(salary_at, rng.randint(1, last_spend_offset), rng), f"{m.upper()} PAYMENT", m, amt, "EXPENSE", "Food", "Dining & Delivery")

        for amt in _split(rng, transport, 10):
            m = rng.choice(TRANSPORT_MERCHANTS)
            add(_at(salary_at, rng.randint(1, last_spend_offset), rng), f"{m.upper()} TRIP", m, amt, "EXPENSE", "Transport")

        for amt in _split(rng, shopping, 3):
            m = rng.choice(SHOPPING_MERCHANTS)
            add(_at(salary_at, rng.randint(1, last_spend_offset), rng), f"{m.upper()} PURCHASE", m, amt, "EXPENSE", "Shopping")

        for amt in _split(rng, ent, 2):
            m = rng.choice(ENTERTAINMENT_MERCHANTS)
            add(_at(salary_at, rng.randint(1, last_spend_offset), rng), f"{m.upper()} BOOKING", m, amt, "EXPENSE", "Entertainment")

        if idx == 5:  # latest cycle: one big, unusual pharmacy + diagnostics bill
            big = 6800
            add(_at(salary_at, 20, rng), "APOLLO PHARMACY + DIAGNOSTICS", "Apollo Pharmacy", big, "EXPENSE", "Healthcare")
            for amt in _split(rng, health - big, 1):
                add(_at(salary_at, 8, rng), "APOLLO PHARMACY", "Apollo Pharmacy", amt, "EXPENSE", "Healthcare")
        else:
            for amt in _split(rng, health, 2):
                add(_at(salary_at, rng.randint(1, last_spend_offset), rng), "APOLLO PHARMACY", "Apollo Pharmacy", amt, "EXPENSE", "Healthcare")

        # Money from other people / refunds so the ledger has non-salary inflows.
        inflow = refund = 0
        if idx == 2:
            inflow = 800
            add(_at(salary_at, 12, rng), "Money received from Rahul", "Rahul", inflow, "TRANSFER_IN", "Transfer")
        if idx == 4:
            refund = 1299
            add(_at(salary_at, 15, rng), "REFUND - AMAZON ORDER RETURN", "Amazon", refund, "REFUND", "Shopping")

        # Sweep the surplus to the user's own savings the day before the next salary.
        surplus = DEMO_SALARY_AMOUNT + inflow + refund - total
        sweep_at = (next_salary_at - timedelta(days=1)).replace(hour=18, minute=0, second=0)
        add(sweep_at, "AUTO SWEEP TO OWN SAVINGS ACCOUNT", "Own Savings Account", surplus, "TRANSFER_OUT", "Transfer")

        out.extend(cycle)

    return sorted(out, key=lambda t: (t.timestamp, 0 if t.transaction_type == "SALARY" else 1))
