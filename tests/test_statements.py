"""Tests for Credit Card Statement Vault, Password Engine, and Ingestion Pipeline."""

import io
from datetime import datetime, timezone
from pathlib import Path

import pypdf
from fastapi.testclient import TestClient

from expense_tracker.app import create_app
from expense_tracker.config import Settings
from expense_tracker.db.models import new_id
from expense_tracker.ingestion.gmail.client import GmailMessage
from expense_tracker.statements.discovery import (
    discover_statement_candidates,
    is_statement_candidate,
)
from expense_tracker.statements.password_engine import (
    AccountProfile,
    Name4Card4Strategy,
    Name4DobDDMMStrategy,
    Name4DobDDMMYYYYStrategy,
    generate_candidate_passwords,
)
from expense_tracker.statements.vault import (
    compute_sha256,
    save_original_statement,
    save_unlocked_statement,
    unlock_pdf,
    validate_pdf,
)


def _create_sample_pdf(password: str | None = None) -> bytes:
    """Create a valid in-memory PDF, optionally encrypted."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    if password:
        writer.encrypt(password)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


# --- Password Strategy Engine Tests ---


def test_account_profile_helpers():
    prof = AccountProfile(name="Gaurav Singh", dob="1995-08-25", card_last4="1234")
    assert prof.get_first_name_4() == "Gaur"
    assert prof.get_dob_parts() == ("25", "08", "1995")

    prof2 = AccountProfile(name="A. B. Kumar", dob="15/05/1990")
    assert prof2.get_first_name_4() == "ABKu"
    assert prof2.get_dob_parts() == ("15", "05", "1990")


def test_password_strategies():
    prof = AccountProfile(name="Gaurav Singh", dob="1995-08-25", card_last4="4321")
    s1 = Name4DobDDMMStrategy()
    cands1 = s1.generate_candidates(prof)
    assert "gaur2508" in cands1
    assert "GAUR2508" in cands1

    s2 = Name4DobDDMMYYYYStrategy()
    cands2 = s2.generate_candidates(prof)
    assert "gaur25081995" in cands2
    assert "GAUR25081995" in cands2

    s3 = Name4Card4Strategy()
    cands3 = s3.generate_candidates(prof)
    assert "gaur4321" in cands3


def test_axis_bank_password_strategy():
    # User's example: C.K. Ajay Kumar + DOB 11.02.1985 -> CKAJ1102, Card 1234 -> CKAJ1234
    prof = AccountProfile(
        name="C.K. Ajay Kumar",
        dob="11.02.1985",
        card_last4="1234",
        issuer="AXIS",
    )
    assert prof.get_first_name_4() == "CKAj"
    assert prof.get_dob_parts() == ("11", "02", "1985")

    cands = generate_candidate_passwords(prof, issuer="AXIS")
    pwd_list = [p for p, _ in cands]
    # Option 1: First four letters in UPPERCASE + DDMM (e.g. CKAJ1102)
    assert "CKAJ1102" in pwd_list
    # Option 2: First four letters in UPPERCASE + card last 4 digits (e.g. CKAJ1234)
    assert "CKAJ1234" in pwd_list


# --- PDF Vault & Unlocking Tests ---


def test_pdf_validation_and_unlock(tmp_path: Path):
    plain_pdf = _create_sample_pdf()
    is_valid, is_enc, pages, err = validate_pdf(plain_pdf)
    assert is_valid is True
    assert is_enc is False
    assert pages == 1

    enc_pdf = _create_sample_pdf(password="secret123")
    is_valid, is_enc, pages, err = validate_pdf(enc_pdf)
    assert is_valid is True
    assert is_enc is True

    # Failed unlock
    ok, res, err = unlock_pdf(enc_pdf, "wrongpassword")
    assert ok is False
    assert res is None

    # Successful unlock
    ok, res, _ = unlock_pdf(enc_pdf, "secret123")
    assert ok is True
    assert res is not None
    # Validate the unlocked PDF
    val_ok, val_enc, val_p, _ = validate_pdf(res)
    assert val_ok is True
    assert val_enc is False
    assert val_p == 1


def test_vault_immutable_storage(tmp_path: Path):
    plain_pdf = _create_sample_pdf()
    stmt_id = new_id()
    orig_path, orig_sha = save_original_statement(tmp_path, "acc123", stmt_id, plain_pdf)
    assert orig_path.exists()
    assert orig_sha == compute_sha256(plain_pdf)

    unl_path, unl_sha = save_unlocked_statement(tmp_path, "acc123", stmt_id, plain_pdf)
    assert unl_path.exists()
    assert unl_sha == compute_sha256(plain_pdf)


# --- Discovery Tests ---


def test_discovery_heuristics():
    msg = GmailMessage(
        id="msg_001",
        thread_id="t_001",
        sender="e-statement@hdfcbank.net",
        subject="HDFC Bank Credit Card Statement for Card ending 4321 for July 2026",
        snippet="Your e-statement is attached",
        received_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        label_ids=[],
        headers={},
        body_text="Dear Customer, attached is your statement",
        body_html=None,
        attachments=[{"filename": "hdfc_statement.pdf", "attachmentId": "att_001"}],
    )
    assert is_statement_candidate(msg) is True

    candidates = discover_statement_candidates([msg])
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.issuer == "HDFC"
    assert cand.card_last4 == "4321"
    assert cand.statement_date is not None
    assert cand.statement_date.month == 7
    assert cand.statement_date.year == 2026

    # Test Scapia email candidate
    scapia_msg = GmailMessage(
        id="msg_002",
        thread_id="t_002",
        sender="Scapia Federal Credit Card <scapiacards@federalbank.co.in>",
        subject="Your Scapia Federal credit card statement for July, 2026",
        snippet="Your credit card statement for 21 Jun 2026 - 20 Jul 2026 is here",
        received_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        label_ids=[],
        headers={},
        body_text="Your credit card statement for 21 Jun 2026 - 20 Jul 2026 is here",
        body_html=None,
        attachments=[{"filename": "Scapia_July_2026.pdf", "attachmentId": "att_002"}],
    )
    assert is_statement_candidate(scapia_msg) is True
    scapia_cands = discover_statement_candidates([scapia_msg])
    assert len(scapia_cands) == 1
    scapia_cand = scapia_cands[0]
    assert scapia_cand.issuer == "SCAPIA"
    assert scapia_cand.statement_date is not None
    assert scapia_cand.statement_date.month == 7
    assert scapia_cand.statement_date.year == 2026

    # Test that Home Loan / Provisional statements are excluded
    loan_msg = GmailMessage(
        id="msg_003",
        thread_id="t_003",
        sender="loansupport@hdfcbank.net",
        subject="HDFC Bank e-Provisional-Statement - Home Loan Account Number - 64xxxx838",
        snippet="Please find attached your provisional statement",
        received_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        label_ids=[],
        headers={},
        body_text="Home Loan Provisional Interest Certificate attached",
        body_html=None,
        attachments=[{"filename": "IT_PROV16656371.pdf", "attachmentId": "att_003"}],
    )
    assert is_statement_candidate(loan_msg) is False
    loan_cands = discover_statement_candidates([loan_msg])
    assert len(loan_cands) == 0

    # Test Bank Account Statement (ICICI Bank Account 0143)
    icici_bank_msg = GmailMessage(
        id="msg_004",
        thread_id="t_004",
        sender="estatements@icicibank.com",
        subject="ICICI Bank Statement from September 01, 2025 to September 30, 2025 for XXXXXXXX0143",
        snippet="Your e-statement for account ending 0143 is attached",
        received_at=datetime(2025, 10, 1, tzinfo=timezone.utc),
        label_ids=[],
        headers={},
        body_text="Dear Customer, find attached your bank statement for account XXXXXXXX0143",
        body_html=None,
        attachments=[{"filename": "Statement_2025MTH09_049537075.pdf", "attachmentId": "att_004"}],
    )
    assert is_statement_candidate(icici_bank_msg) is True
    icici_cands = discover_statement_candidates([icici_bank_msg])
    assert len(icici_cands) == 1
    icici_cand = icici_cands[0]
    assert icici_cand.issuer == "ICICI"
    assert icici_cand.statement_type == "BANK_ACCOUNT"
    assert icici_cand.card_last4 == "0143"
    assert icici_cand.statement_date is not None
    assert icici_cand.statement_date.month == 9
    assert icici_cand.statement_date.year == 2025

    # Test Axis Bank Statement (Money Quotient for July 2026)
    axis_msg = GmailMessage(
        id="msg_007",
        thread_id="t_007",
        sender="statements@axis.bank.in",
        subject="Axis Bank Statement : Money Quotient for July 2026",
        snippet="Please find attached your statement for July 2026",
        received_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        label_ids=[],
        headers={"to": "gaurav.singh.86@gmail.com", "from": "statements@axis.bank.in"},
        body_text="Axis Bank statement attached",
        body_html=None,
        attachments=[{"filename": "Axis_Statement_July_2026.pdf", "attachmentId": "att_007"}],
    )
    assert is_statement_candidate(axis_msg) is True
    axis_cands = discover_statement_candidates([axis_msg])
    assert len(axis_cands) == 1
    axis_cand = axis_cands[0]
    assert axis_cand.issuer == "AXIS"
    assert axis_cand.statement_type == "BANK_ACCOUNT"
    assert axis_cand.statement_date is not None
    assert axis_cand.statement_date.month == 7
    assert axis_cand.statement_date.year == 2026

    # Test Axis Credit Card Statement from cc.statements@axis.bank.in
    axis_cc_msg = GmailMessage(
        id="msg_008",
        thread_id="t_008",
        sender="cc.statements@axis.bank.in",
        subject="Your Axis Rewards Credit Card ending XX51 - July 2026",
        snippet="Please find attached your credit card statement for July 2026",
        received_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        label_ids=[],
        headers={"to": "gaurav.singh.86@gmail.com", "from": "cc.statements@axis.bank.in"},
        body_text="Credit Card statement attached",
        body_html=None,
        attachments=[{"filename": "Credit Card Statement.pdf", "attachmentId": "att_008"}],
    )
    assert is_statement_candidate(axis_cc_msg) is True
    axis_cc_cands = discover_statement_candidates([axis_cc_msg])
    assert len(axis_cc_cands) == 1
    assert axis_cc_cands[0].issuer == "AXIS"
    assert axis_cc_cands[0].statement_type == "CREDIT_CARD"

    # Test KFS / MITC disclosure sheets are excluded
    kfs_msg = GmailMessage(
        id="msg_005",
        thread_id="t_005",
        sender="scapiacards@federalbank.co.in",
        subject="Important Information: Key Fact Statement (KFS) for your Credit Card",
        snippet="Please find attached your Key Fact Statement",
        received_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
        label_ids=[],
        headers={},
        body_text="KFS attached",
        body_html=None,
        attachments=[{"filename": "KFS_Scapia_Federal_Credit_Card.pdf", "attachmentId": "att_005"}],
    )
    assert is_statement_candidate(kfs_msg) is False
    kfs_cands = discover_statement_candidates([kfs_msg])
    assert len(kfs_cands) == 0

    # Test statement addressed to gauravsingh86@gmail.com (no dots) is excluded
    undotted_msg = GmailMessage(
        id="msg_006",
        thread_id="t_006",
        sender="estatements@icicibank.com",
        subject="ICICI Bank Statement for account ending 0143",
        snippet="statement",
        received_at=datetime(2025, 10, 1, tzinfo=timezone.utc),
        label_ids=[],
        headers={"to": "gauravsingh86@gmail.com"},
        body_text="statement",
        body_html=None,
        attachments=[{"filename": "Statement_0143.pdf", "attachmentId": "att_006"}],
    )
    assert is_statement_candidate(undotted_msg) is False

    # Test eforex@axisbank.com statement email is excluded
    eforex_msg = GmailMessage(
        id="msg_eforex_01",
        thread_id="t_eforex",
        sender="eforex@axisbank.com",
        subject="Axis Bank Forex Card Statement for July 2026",
        snippet="Forex card statement attached",
        received_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        label_ids=[],
        headers={"to": "gaurav.singh.86@gmail.com", "from": "eforex@axisbank.com"},
        body_text="Dear Customer, find attached your Forex Card statement",
        body_html=None,
        attachments=[{"filename": "Forex_Statement.pdf", "attachmentId": "att_forex_01"}],
    )
    assert is_statement_candidate(eforex_msg) is False
    eforex_cands = discover_statement_candidates([eforex_msg])
    assert len(eforex_cands) == 0


# --- Ingestion & Pipeline Tests ---


def test_ingestion_encrypted_statement_with_profile(tmp_path: Path):
    settings = Settings(
        app={"data_dir": tmp_path},
        database={"filename": "test.db"},
    )
    app = create_app(settings)
    client = TestClient(app)

    # 1. Create Credit Card Account
    acc_res = client.post(
        "/api/accounts",
        json={
            "name": "HDFC Regalia Credit Card",
            "account_type": "CREDIT_CARD",
            "is_asset": False,
            "is_liability": True,
            "card_last4": "5678",
            "currency": "INR",
        },
    )
    assert acc_res.status_code == 200
    account_id = acc_res.json()["id"]

    # 2. Configure Password Profile
    prof_res = client.put(
        f"/api/accounts/{account_id}/password-profile",
        json={
            "issuer": "HDFC",
            "strategy": "NAME4_DDMM",
            "configuration": {
                "name": "Gaurav Singh",
                "dob": "1995-08-25",
                "card_last4": "5678",
            },
        },
    )
    assert prof_res.status_code == 200

    # 3. Create encrypted PDF with password "gaur2508"
    enc_pdf = _create_sample_pdf(password="gaur2508")

    # 4. Upload statement
    upload_res = client.post(
        "/api/statements/upload",
        files={"file": ("hdfc_statement_5678.pdf", enc_pdf, "application/pdf")},
        data={"account_id": account_id, "issuer": "HDFC", "card_last4": "5678"},
    )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["status"] in ("READY_FOR_EXTRACTION", "VALIDATED", "REVIEW_REQUIRED")
    assert data["is_encrypted"] is True
    assert data["password_strategy_id"] == "NAME4_DDMM"
    assert data["has_original_file"] is True
    assert data["has_unlocked_file"] is True
    assert len(data["events"]) >= 4

    statement_id = data["id"]

    # 5. Fetch statement detail
    detail_res = client.get(f"/api/statements/{statement_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] in ("READY_FOR_EXTRACTION", "VALIDATED", "REVIEW_REQUIRED")

    # 6. Download original and unlocked files
    orig_file_res = client.get(f"/api/statements/{statement_id}/file/original")
    assert orig_file_res.status_code == 200
    assert orig_file_res.headers["content-type"] == "application/pdf"

    unl_file_res = client.get(f"/api/statements/{statement_id}/file/unlocked")
    assert unl_file_res.status_code == 200
    assert unl_file_res.headers["content-type"] == "application/pdf"

    # 7. List account statements
    acc_stmts_res = client.get(f"/api/accounts/{account_id}/statements")
    assert acc_stmts_res.status_code == 200
    assert len(acc_stmts_res.json()["statements"]) == 1


def test_ingestion_encrypted_statement_manual_unlock(tmp_path: Path):
    settings = Settings(
        app={"data_dir": tmp_path},
        database={"filename": "test.db"},
    )
    app = create_app(settings)
    client = TestClient(app)

    # 1. Create ICICI Credit Card Account without password profile
    acc_res = client.post(
        "/api/accounts",
        json={
            "name": "ICICI Sapphiro",
            "account_type": "CREDIT_CARD",
            "is_asset": False,
            "is_liability": True,
            "card_last4": "9999",
            "currency": "INR",
        },
    )
    account_id = acc_res.json()["id"]

    # 2. Upload statement with custom password
    enc_pdf = _create_sample_pdf(password="MyHardPassword99")
    upload_res = client.post(
        "/api/statements/upload",
        files={"file": ("icici_statement.pdf", enc_pdf, "application/pdf")},
        data={"account_id": account_id, "issuer": "ICICI", "card_last4": "9999"},
    )
    assert upload_res.status_code == 200
    stmt_data = upload_res.json()
    assert stmt_data["status"] in ("PASSWORD_REQUIRED", "PASSWORD_FAILED")
    statement_id = stmt_data["id"]

    # 3. Wrong password unlock attempt
    bad_unlock = client.post(
        f"/api/statements/{statement_id}/unlock",
        json={"password": "wrong", "save_to_profile": False},
    )
    assert bad_unlock.status_code == 400

    # 4. Correct password unlock attempt
    good_unlock = client.post(
        f"/api/statements/{statement_id}/unlock",
        json={"password": "MyHardPassword99", "save_to_profile": True},
    )
    assert good_unlock.status_code == 200
    assert good_unlock.json()["status"] in ("READY_FOR_EXTRACTION", "VALIDATED", "REVIEW_REQUIRED")
    assert good_unlock.json()["has_unlocked_file"] is True

    # 5. Verify password profile was updated — the API redacts the raw
    # password from responses (it must never be echoed back over HTTP), but
    # the account can still auto-unlock future statements with it.
    prof_res = client.get(f"/api/accounts/{account_id}/password-profile")
    assert prof_res.status_code == 200
    assert prof_res.json()["configured"] is True
    assert prof_res.json()["configuration"]["custom_password"] is None
    assert prof_res.json()["configuration"]["has_custom_password"] is True

    from expense_tracker.db.models import PasswordProfile
    from expense_tracker.db.session import get_session_factory
    from sqlalchemy import select

    session = get_session_factory()()
    try:
        stored = session.scalars(
            select(PasswordProfile).where(PasswordProfile.account_id == account_id)
        ).first()
        assert stored is not None
        assert stored.configuration["custom_password"] == "MyHardPassword99"
    finally:
        session.close()


def test_statement_transaction_match_api(tmp_path: Path):
    """Test confirming and rejecting statement transaction matches."""
    from expense_tracker.db.models import CreditCardStatement, StatementTransaction
    from expense_tracker.db.session import get_session_factory

    settings = Settings(
        app={"data_dir": tmp_path},
        database={"filename": "test.db"},
    )
    app = create_app(settings)
    client = TestClient(app)

    session = get_session_factory()()
    try:
        # Create a statement with a transaction
        stmt = CreditCardStatement(
            id=new_id(),
            issuer="AXIS",
            original_filename="axis_test.pdf",
            status="VALIDATED",
            validation_status="VALIDATED",
        )
        session.add(stmt)
        session.flush()

        tx = StatementTransaction(
            id=new_id(),
            statement_id=stmt.id,
            transaction_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
            description="NOBROKER TECHNOLOGIES",
            amount=6858.00,
            debit_amount=6858.00,
            match_status="POSSIBLE_MATCH",
            match_confidence=0.75,
            match_reason="Exact amount, Same date",
        )
        session.add(tx)
        session.commit()

        statement_id = stmt.id
        tx_id = tx.id
    finally:
        session.close()

    # 1. Confirm Match
    confirm_res = client.post(
        f"/api/statements/{statement_id}/transactions/{tx_id}/match",
        json={"match_status": "MATCHED", "match_reason": "Manually confirmed by user"},
    )
    assert confirm_res.status_code == 200
    data = confirm_res.json()
    assert data["success"] is True
    updated_txs = data["statement"]["transactions"]
    matched_tx = next(t for t in updated_txs if t["id"] == tx_id)
    assert matched_tx["match_status"] == "MATCHED"
    assert matched_tx["match_confidence"] == 1.0
    assert "Manually confirmed" in matched_tx["match_reason"]

    # 2. Reject Match / Mark Unmatched
    reject_res = client.post(
        f"/api/statements/{statement_id}/transactions/{tx_id}/match",
        json={"match_status": "UNMATCHED", "match_reason": "Marked as non-match by user"},
    )
    assert reject_res.status_code == 200
    data2 = reject_res.json()
    assert data2["success"] is True
    updated_txs2 = data2["statement"]["transactions"]
    unmatched_tx = next(t for t in updated_txs2 if t["id"] == tx_id)
    assert unmatched_tx["match_status"] == "UNMATCHED"
    assert unmatched_tx["match_confidence"] == 0.0


def test_emi_detection_and_ledger_import(tmp_path: Path):
    """Test parsing, grouping, and importing EMI line items (Principal, Interest, GST)."""
    from expense_tracker.db.models import CreditCardStatement, StatementTransaction
    from expense_tracker.db.session import get_session_factory
    from expense_tracker.statements.emi import parse_emi_details, categorize_statement_line_item

    # 1. Test Regex parsing
    emi_p = parse_emi_details("EMI PRINCIPAL - 7/9, REF# 68265776 MEDICAL")
    assert emi_p is not None
    assert emi_p["type"] == "PRINCIPAL"
    assert emi_p["installment"] == 7
    assert emi_p["tenure"] == 9
    assert emi_p["ref_id"] == "68265776"
    assert emi_p["merchant"] == "MEDICAL"

    emi_i = parse_emi_details("EMI INTEREST - 7/9, REF# 68265776 MEDICAL")
    assert emi_i is not None
    assert emi_i["type"] == "INTEREST"
    assert emi_i["installment"] == 7

    # 2. Test Smart Categorization
    cat_p, _, dir_p, _ = categorize_statement_line_item("EMI PRINCIPAL - 7/9, REF# 68265776 MEDICAL", 8464.00)
    assert cat_p == "healthcare"

    cat_i, sub_i, _, _ = categorize_statement_line_item("EMI INTEREST - 7/9, REF# 68265776 MEDICAL", 387.00)
    assert cat_i == "fees-interest"
    assert sub_i == "emi-interest"

    cat_g, sub_g, _, _ = categorize_statement_line_item("GST", 69.66)
    assert cat_g == "fees-interest"
    assert sub_g == "gst"

    # 3. Test Import Endpoint
    settings = Settings(
        app={"data_dir": tmp_path},
        database={"filename": "test.db"},
    )
    app = create_app(settings)
    client = TestClient(app)

    session = get_session_factory()()
    try:
        stmt = CreditCardStatement(
            id=new_id(),
            issuer="AXIS",
            card_last4="4951",
            original_filename="axis_cc.pdf",
            status="VALIDATED",
            validation_status="VALIDATED",
        )
        session.add(stmt)
        session.flush()

        tx_p = StatementTransaction(
            id=new_id(),
            statement_id=stmt.id,
            transaction_date=datetime(2026, 8, 10, tzinfo=timezone.utc),
            description="EMI PRINCIPAL - 7/9, REF# 68265776 MEDICAL",
            amount=8464.00,
            debit_amount=8464.00,
            match_status="UNMATCHED",
        )
        tx_i = StatementTransaction(
            id=new_id(),
            statement_id=stmt.id,
            transaction_date=datetime(2026, 8, 10, tzinfo=timezone.utc),
            description="EMI INTEREST - 7/9, REF# 68265776 MEDICAL",
            amount=387.00,
            debit_amount=387.00,
            match_status="UNMATCHED",
        )
        tx_g = StatementTransaction(
            id=new_id(),
            statement_id=stmt.id,
            transaction_date=datetime(2026, 8, 10, tzinfo=timezone.utc),
            description="GST",
            amount=69.66,
            debit_amount=69.66,
            match_status="UNMATCHED",
        )
        session.add_all([tx_p, tx_i, tx_g])
        session.commit()

        stmt_id = stmt.id
        bundle_ids = [tx_p.id, tx_i.id, tx_g.id]
    finally:
        session.close()

    # Import bundle
    bundle_res = client.post(
        f"/api/statements/{stmt_id}/import-bundle",
        json={"transaction_ids": bundle_ids},
    )
    assert bundle_res.status_code == 200
    b_data = bundle_res.json()
    assert b_data["success"] is True
    assert b_data["imported_count"] == 3

    # Verify all 3 transactions are now MATCHED in statement
    updated_txs = b_data["statement"]["transactions"]
    for b_id in bundle_ids:
        found = next(t for t in updated_txs if t["id"] == b_id)
        assert found["match_status"] == "MATCHED"
        assert found["matched_transaction_id"] is not None

    # 4. Re-running reconcile does NOT overwrite imported/confirmed matches
    recon_res = client.post(f"/api/statements/{stmt_id}/reconcile")
    assert recon_res.status_code == 200
    recon_txs = recon_res.json()["statement"]["transactions"]
    for b_id in bundle_ids:
        found = next(t for t in recon_txs if t["id"] == b_id)
        assert found["match_status"] == "MATCHED"
        assert found["matched_transaction_id"] is not None


def test_upi_rrn_exact_reconciliation_matching(tmp_path: Path):
    """Test 12-digit UPI RRN deterministic matching between statement and ledger alerts."""
    from expense_tracker.db.models import StatementTransaction, Transaction
    from expense_tracker.statements.reconciliation import extract_upi_rrn, match_statement_transaction

    # 1. Verify RRN Extraction
    stmt_desc = "UPI/P2M/934010689696/Syed Naseeruddin /Paymen/YES BANK LIMITED YBS"
    rrn = extract_upi_rrn(stmt_desc)
    assert rrn == "934010689696"

    # 2. Test Deterministic Match
    stmt_tx = StatementTransaction(
        id=new_id(),
        statement_id="stmt-1",
        transaction_date=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc),
        description=stmt_desc,
        amount=20.00,
        debit_amount=20.00,
    )

    ledger_tx = Transaction(
        id=new_id(),
        source="gmail:axis",
        transaction_date=datetime(2026, 7, 27, 8, 0, 44, tzinfo=timezone.utc),
        amount=20.00,
        currency="INR",
        direction="outflow",
        reference_number="934010689696",
        description="UPI/P2M/934010689696/Syed Naseeruddin",
    )

    res = match_statement_transaction(stmt_tx, [ledger_tx])
    assert res.status == "MATCHED"
    assert res.matched_transaction_id == ledger_tx.id
    assert res.score == 1.0
    assert "934010689696" in res.reason




