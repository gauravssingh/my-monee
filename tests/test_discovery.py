from expense_tracker.ingestion.discovery import load_discovery_rules
from expense_tracker.ingestion.gmail.client import GmailMessage
from datetime import datetime, timezone


def test_discovery_skips_otp_and_accepts_spend() -> None:
    rules = load_discovery_rules()
    otp = GmailMessage(
        id="1",
        thread_id=None,
        sender="alerts@bank.com",
        subject="Your OTP for login is 111111",
        snippet="otp",
        received_at=datetime.now(timezone.utc),
        label_ids=[],
        headers={},
        body_text="OTP 111111",
        body_html=None,
    )
    spend = GmailMessage(
        id="2",
        thread_id=None,
        sender="alerts@hdfcbank.net",
        subject="Alert : transaction of Rs.100",
        snippet="spent",
        received_at=datetime.now(timezone.utc),
        label_ids=[],
        headers={},
        body_text="Rs.100 spent at MERCHANT",
        body_html=None,
    )
    assert rules.is_financial_candidate(otp)[0] is False
    assert rules.is_financial_candidate(spend)[0] is True
    provider, score = rules.detect_provider(spend)
    assert provider == "hdfc_alerts"
    assert score >= 0.35
