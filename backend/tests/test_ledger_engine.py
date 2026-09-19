from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.ledger import INITIAL_CYCLE_KEY, LedgerTxn, rebuild, signed_amount

IST = timezone(timedelta(hours=5, minutes=30))
D = Decimal

_seq = 0


def tx(id_, ts, typ, amount, **meta):
    global _seq
    _seq += 1
    return LedgerTxn(id=id_, timestamp=ts, seq=_seq, transaction_type=typ, amount=D(str(amount)), metadata=meta)


SALARY_TS = datetime(2026, 9, 30, 11, 27, 4, tzinfo=IST)


def cycle_of(result, txn_id):
    key = result.txns[txn_id].cycle_key
    return next(c for c in result.cycles if c.key == key)


def test_opening_balance_is_not_income():
    r = rebuild(D("35000"), [tx("e1", SALARY_TS, "EXPENSE", 100)])
    (cycle,) = r.cycles
    assert cycle.income_total == 0
    assert cycle.key == INITIAL_CYCLE_KEY
    assert r.final_balance == D("34900.00")


def test_salary_increases_balance_and_keeps_existing_money_out_of_income():
    r = rebuild(D("35000"), [tx("s", SALARY_TS, "SALARY", 100000)])
    (cycle,) = r.cycles
    assert r.txns["s"].balance_after == D("135000.00")
    assert cycle.income_total == D("100000.00")  # NOT 135,000
    assert cycle.carried_over_balance == D("35000.00")
    assert cycle.opening_balance == D("135000.00")  # balance right after salary


def test_salary_starts_new_cycle_and_closes_previous_at_exact_timestamp():
    old_salary = datetime(2026, 8, 31, 11, 27, 4, tzinfo=IST)
    before = SALARY_TS - timedelta(minutes=1)  # 11:26:04
    after = SALARY_TS + timedelta(minutes=8)  # 11:35:04
    r = rebuild(
        D("35000"),
        [
            tx("s0", old_salary, "SALARY", 100000),
            tx("e_before", before, "EXPENSE", 500),
            tx("s1", SALARY_TS, "SALARY", 100000),
            tx("e_after", after, "EXPENSE", 160),
        ],
    )
    assert len(r.cycles) == 2
    prev, cur = r.cycles
    assert prev.status == "CLOSED" and prev.end_at == SALARY_TS
    assert cur.status == "ACTIVE" and cur.end_at is None and cur.start_at == SALARY_TS
    # expense before the salary belongs to the previous cycle, after -> new cycle
    assert cycle_of(r, "e_before") is prev
    assert cycle_of(r, "e_after") is cur
    assert prev.expense_total == D("500.00")
    assert cur.expense_total == D("160.00")  # counter starts at zero after salary


def test_salary_transaction_itself_belongs_to_new_cycle():
    r = rebuild(D("0"), [tx("s0", SALARY_TS - timedelta(days=30), "SALARY", 1000), tx("s1", SALARY_TS, "SALARY", 1000)])
    assert cycle_of(r, "s1").salary_transaction_id == "s1"


def test_expense_at_same_instant_as_salary_goes_to_new_cycle_regardless_of_insert_order():
    r = rebuild(
        D("0"),
        [
            tx("e", SALARY_TS, "EXPENSE", 10),  # inserted first (lower seq)
            tx("s", SALARY_TS, "SALARY", 1000),
        ],
    )
    assert cycle_of(r, "e") is cycle_of(r, "s")


def test_transfer_in_raises_balance_but_is_not_salary_or_income():
    r = rebuild(
        D("0"),
        [tx("s", SALARY_TS, "SALARY", 100000), tx("r", SALARY_TS + timedelta(minutes=13), "TRANSFER_IN", 1000)],
    )
    cur = r.cycles[0]
    assert r.final_balance == D("101000.00")
    assert cur.income_total == D("100000.00")
    assert cur.other_inflow_total == D("1000.00")
    assert len(r.cycles) == 1  # a transfer never starts a cycle


def test_expense_decreases_balance_and_balance_after_is_recorded_per_row():
    r = rebuild(
        D("35000"),
        [
            tx("s", SALARY_TS, "SALARY", 100000),
            tx("sw", SALARY_TS + timedelta(minutes=8), "EXPENSE", 160),
            tx("rahul", SALARY_TS + timedelta(minutes=13), "TRANSFER_IN", 1000),
        ],
    )
    assert r.txns["s"].balance_after == D("135000.00")
    assert r.txns["sw"].balance_after == D("134840.00")
    assert r.txns["rahul"].balance_after == D("135840.00")
    assert r.final_balance == D("135840.00")


def test_refund_and_interest_directions():
    r = rebuild(D("1000"), [tx("e", SALARY_TS, "EXPENSE", 300), tx("f", SALARY_TS + timedelta(hours=1), "REFUND", 200), tx("i", SALARY_TS + timedelta(hours=2), "INTEREST", 5)])
    assert r.final_balance == D("905.00")
    assert r.cycles[0].refund_total == D("200.00")
    assert r.cycles[0].income_total == D("5.00")


def test_history_is_preserved_when_a_new_cycle_starts():
    old = datetime(2026, 8, 31, 11, 27, 4, tzinfo=IST)
    base = [
        tx("s0", old, "SALARY", 100000),
        tx("a", old + timedelta(days=3), "EXPENSE", 42500),
    ]
    before = rebuild(D("35000"), base)
    after = rebuild(D("35000"), base + [tx("s1", SALARY_TS, "SALARY", 100000), tx("b", SALARY_TS + timedelta(minutes=8), "EXPENSE", 160)])
    old_cycle_before = before.cycles[0]
    old_cycle_after = after.cycles[0]
    assert old_cycle_after.expense_total == old_cycle_before.expense_total == D("42500.00")
    assert old_cycle_after.status == "CLOSED"
    assert after.txns["a"].balance_after == before.txns["a"].balance_after


def test_backdated_transaction_is_slotted_into_the_right_cycle_and_balances_recomputed():
    old = datetime(2026, 8, 31, 11, 27, 4, tzinfo=IST)
    r1 = rebuild(D("0"), [tx("s0", old, "SALARY", 1000), tx("s1", SALARY_TS, "SALARY", 1000)])
    r2 = rebuild(D("0"), [tx("s0", old, "SALARY", 1000), tx("s1", SALARY_TS, "SALARY", 1000), tx("late", old + timedelta(days=5), "EXPENSE", 250)])
    assert r2.txns["s1"].balance_after == r1.txns["s1"].balance_after - D("250")
    assert cycle_of(r2, "late").key == "s0"


def test_rebuild_is_deterministic_regardless_of_input_order():
    items = [tx("s", SALARY_TS, "SALARY", 5), tx("e", SALARY_TS + timedelta(hours=1), "EXPENSE", 2), tx("r", SALARY_TS + timedelta(hours=2), "TRANSFER_IN", 1)]
    a = rebuild(D("10"), items)
    b = rebuild(D("10"), list(reversed(items)))
    assert {k: v.balance_after for k, v in a.txns.items()} == {k: v.balance_after for k, v in b.txns.items()}


def test_other_type_direction_defaults_to_debit_unless_credit_metadata():
    assert signed_amount("OTHER", D("10")) == D("-10.00")
    assert signed_amount("OTHER", D("10"), {"direction": "credit"}) == D("10.00")


def test_amount_must_be_positive_and_naive_timestamps_rejected():
    with pytest.raises(ValueError):
        signed_amount("EXPENSE", D("-5"))
    with pytest.raises(ValueError):
        rebuild(D("0"), [LedgerTxn("x", datetime(2026, 1, 1), 1, "EXPENSE", D("5"), {})])
