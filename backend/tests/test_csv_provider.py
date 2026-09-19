from decimal import Decimal

from app.providers.csv_provider import parse_csv


def test_supplied_demo_csv_format_maps_to_ledger_types():
    text = (
        "date,description,merchant,amount,type,category,source,currency\n"
        "2026-09-01,SALARY CREDIT,Employer,100000,income,Salary,csv,INR\n"
        "2026-09-02,SWIGGY ORDER,Swiggy,160,expense,Food,csv,INR\n"
        "2026-09-03,Money received from Rahul,Rahul,1000,transfer,Transfer,csv,INR\n"
        "2026-09-04,Transfer to own savings,,5000,transfer,Transfer,csv,INR\n"
        "2026-09-05,AMAZON REFUND,Amazon,500,income,,csv,INR\n"
    )
    rows, errors = parse_csv(text)
    assert not errors
    assert [r.transaction_type for r in rows] == ["SALARY", "EXPENSE", "TRANSFER_IN", "TRANSFER_OUT", "REFUND"]
    assert all(r.amount > 0 for r in rows)
    assert rows[0].timestamp.hour == 9 and rows[0].timestamp.utcoffset().total_seconds() == 19800  # date-only -> 09:00 IST


def test_exact_ledger_types_and_full_timestamps_are_respected():
    rows, errors = parse_csv("timestamp,description,amount,transaction_type\n2026-09-30T11:27:04+05:30,Salary,100000,SALARY\n")
    assert not errors and rows[0].transaction_type == "SALARY"
    assert (rows[0].timestamp.hour, rows[0].timestamp.minute, rows[0].timestamp.second) == (11, 27, 4)


def test_signed_amounts_without_a_type_column():
    rows, _ = parse_csv("date,narration,amount\n2026-09-01,Cafe,-250\n2026-09-02,Salary from ACME,90000\n")
    assert [(r.transaction_type, r.amount) for r in rows] == [("EXPENSE", Decimal("250")), ("SALARY", Decimal("90000"))]


def test_bad_rows_are_reported_not_silently_dropped():
    rows, errors = parse_csv("date,description,amount\n2026-09-01,ok,10\nnope,bad date,10\n2026-09-01,bad amount,abc\n2026-09-01,,10\n2026-09-01,zero,0\n")
    assert len(rows) == 1 and len(errors) == 4 and "Row 3" in errors[0]


def test_missing_columns_and_empty_file():
    assert "Missing required column" in parse_csv("foo,bar\n1,2\n")[1][0]
    assert parse_csv("")[1]


def test_external_ids_are_stable_and_distinguish_identical_rows():
    text = "date,description,amount,type\n2026-09-01,Tea,20,expense\n2026-09-01,Tea,20,expense\n"
    a, _ = parse_csv(text)
    b, _ = parse_csv(text)
    assert [r.external_id for r in a] == [r.external_id for r in b]
    assert a[0].external_id != a[1].external_id


def test_rupee_symbols_and_thousands_separators():
    rows, errors = parse_csv('date,description,amount,type\n2026-09-01,Rent,"₹15,000",expense\n')
    assert not errors and rows[0].amount == Decimal("15000")


def test_ambiguous_transfer_direction_is_rejected_not_guessed():
    rows, errors = parse_csv("date,description,amount,type\n2026-09-01,Transfer,500,transfer\n")
    assert not rows and "incoming or outgoing" in errors[0]
