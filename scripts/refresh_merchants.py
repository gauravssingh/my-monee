"""Refresh merchant registry and links from all transactions in the ledger."""

from __future__ import annotations

import argparse
import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.db.session import get_session_factory
from expense_tracker.db.models import Email, Transaction, Merchant, MerchantAlias
from expense_tracker.merchants.normalize import normalize_merchant


def clean_raw_merchant(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    # Remove trailing warning banners or sentences sometimes captured by regex
    cleaned = re.split(
        r"(?:If\s+this\s+transaction|To\s+check\s+your|If\s+you\s+did\s+not|Please\s+SMS|Should\s+you\s+wish)",
        cleaned,
        flags=re.I,
    )[0].strip()
    cleaned = re.sub(r"^(RAZ\*|PYU\*|PAYTM\*|GPAY\*)", "", cleaned, flags=re.I).strip()
    return cleaned if cleaned else None


def extract_merchant_from_context(desc: str | None, email: Email | None) -> tuple[str | None, str | None]:
    subj = email.subject if email else ""
    body = (email.body_text or "")[:400] if email else ""
    blob = f"{desc or ''} {subj} {body}"

    # Known merchant signatures
    if re.search(r"swiggy", blob, re.I):
        return "Swiggy", "Swiggy"
    if re.search(r"decathlon", blob, re.I):
        return "Decathlon", "Decathlon"
    if re.search(r"nobroker", blob, re.I):
        return "NoBrokerHood", "NoBrokerHood"
    if re.search(r"\bjio\b", blob, re.I):
        return "Jio", "Jio"
    if re.search(r"ixigo", blob, re.I):
        return "ixigo", "ixigo"
    if re.search(r"keyslo", blob, re.I):
        return "Keyslo", "Keyslo"
    if re.search(r"\bapple\b", blob, re.I):
        return "Apple Inc", "Apple Inc"
    if re.search(r"amazon\s*fresh|amazon\s*pay|amazon\.in|\bamazon\b", blob, re.I):
        return "Amazon India", "Amazon India"
    if re.search(r"act\s*broadband|\bact\b.*broadband|broadband bill", blob, re.I):
        return "ACT Broadband", "ACT Broadband"
    if re.search(r"tata\s*play", blob, re.I):
        return "Tata Play", "Tata Play"
    if re.search(r"zomato", blob, re.I):
        return "Zomato", "Zomato"
    if re.search(r"uber", blob, re.I):
        return "Uber", "Uber"
    if re.search(r"ola\b", blob, re.I):
        return "Ola", "Ola"
    if re.search(r"bigbasket|bbdaily", blob, re.I):
        return "BigBasket", "BigBasket"
    if re.search(r"blinkit|grofers", blob, re.I):
        return "Blinkit", "Blinkit"
    if re.search(r"zepto", blob, re.I):
        return "Zepto", "Zepto"
    if re.search(r"airtel", blob, re.I):
        return "Airtel", "Airtel"

    return None, None


def resolve_or_create_merchant(
    session: Session,
    raw_val: str,
    norm_val: str,
    display_override: str | None = None,
) -> str:
    # 1. Check alias
    alias = session.scalar(select(MerchantAlias).where(MerchantAlias.alias_raw == raw_val).limit(1))
    if alias:
        return alias.merchant_id

    # 2. Check normalized_key
    norm_key = norm_val.lower().replace(" ", "_").replace("*", "").replace("-", "_").strip("_")
    merchant = session.scalar(select(Merchant).where(Merchant.normalized_key == norm_key).limit(1))
    if merchant:
        return merchant.id

    # 3. Create new Merchant
    display_name = display_override or (raw_val.upper() if len(raw_val) < 4 else raw_val.title())
    merchant = Merchant(
        display_name=display_name,
        normalized_key=norm_key,
        canonical_name=None,
    )
    session.add(merchant)
    session.flush()

    # Add primary alias
    alias_norm_key = raw_val.lower().replace(" ", "_").replace("*", "").replace("-", "_").strip("_")
    existing_alias_norm = session.scalar(select(MerchantAlias).where(MerchantAlias.alias_normalized == alias_norm_key).limit(1))
    if not existing_alias_norm:
        try:
            alias = MerchantAlias(
                merchant_id=merchant.id,
                alias_raw=raw_val,
                alias_normalized=alias_norm_key,
                source="refresh",
            )
            session.add(alias)
            session.flush()
        except Exception:
            session.rollback()

    return merchant.id


def refresh_merchants(*, apply: bool = False) -> None:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        # Get Unknown Merchant entity
        unk_merchant = session.scalar(select(Merchant).where(Merchant.normalized_key == "unknown_merchant").limit(1))
        unk_id = unk_merchant.id if unk_merchant else None

        # Fetch all non-transfer transactions
        txs = session.scalars(
            select(Transaction).where(Transaction.is_transfer.is_(False))
        ).all()

        print(f"Total non-transfer transactions to check: {len(txs)}")

        relinked = 0
        extracted = 0

        for tx in txs:
            raw = clean_raw_merchant(tx.merchant_raw)
            norm = normalize_merchant(raw) if raw else None

            # If missing raw, try to extract from description/email
            if not raw or raw == "Unknown Merchant" or raw == "None":
                email = session.get(Email, tx.source_email_id) if tx.source_email_id else None
                ext_raw, ext_norm = extract_merchant_from_context(tx.description, email)
                if ext_raw:
                    raw = ext_raw
                    norm = ext_norm
                    extracted += 1
                    if apply:
                        tx.merchant_raw = raw
                        tx.merchant_normalized = norm

            if not raw or raw == "Unknown Merchant":
                # Leave as Unknown Merchant
                if apply and unk_id:
                    tx.merchant_entity_id = unk_id
                continue

            # We have a valid raw and norm
            target_norm = norm or raw.title()
            merchant_id = resolve_or_create_merchant(session, raw, target_norm, display_override=target_norm)

            if tx.merchant_entity_id != merchant_id:
                relinked += 1
                if apply:
                    tx.merchant_raw = raw
                    tx.merchant_normalized = target_norm
                    tx.merchant_entity_id = merchant_id

        if apply:
            session.commit()
            print(f"Successfully refreshed merchants! Newly extracted: {extracted}, Relinked transactions: {relinked}")
        else:
            print(f"[DRY-RUN] Would extract {extracted} missing merchants and relink {relinked} transactions to proper merchant profiles. Pass --apply to persist.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh merchant registry from transactions.")
    parser.add_argument("--apply", action="store_true", help="Apply updates to database.")
    args = parser.parse_args()
    refresh_merchants(apply=args.apply)
