from datetime import datetime, timezone

from mymonee.parsers.extract import dates_look_day_month_swapped, parse_date_near_amount


def test_iso_date_not_swapped_by_dayfirst() -> None:
    fallback = datetime(2026, 5, 10, 16, 46, tzinfo=timezone.utc)
    text = "Date and Time: 2026-05-10 22:16:03 Paid to: Huts & Hives"
    parsed = parse_date_near_amount(text, fallback)
    assert parsed is not None
    assert parsed.date().isoformat() == "2026-05-10"


def test_indian_numeric_dayfirst() -> None:
    fallback = datetime(2026, 5, 10, tzinfo=timezone.utc)
    parsed = parse_date_near_amount("debited on 10/05/2026 at SWIGGY", fallback)
    assert parsed is not None
    assert parsed.date().isoformat() == "2026-05-10"


def test_ambiguous_numeric_prefers_email_received() -> None:
    fallback = datetime(2026, 5, 10, tzinfo=timezone.utc)
    # 05/10/2026 is ambiguous; should follow received_at (May 10)
    parsed = parse_date_near_amount("txn on 05/10/2026", fallback)
    assert parsed is not None
    assert parsed.date().isoformat() == "2026-05-10"


def test_swapped_detector() -> None:
    parsed = datetime(2026, 10, 5, tzinfo=timezone.utc)
    reference = datetime(2026, 5, 10, 16, 46, tzinfo=timezone.utc)
    assert dates_look_day_month_swapped(parsed, reference)
    assert not dates_look_day_month_swapped(reference, reference)
