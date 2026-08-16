"""Normalize and classify merchants in groups 1-7 in SQLite ledger."""

from __future__ import annotations

import argparse
from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.db.session import get_session_factory
from expense_tracker.db.models import Transaction, Category, Subcategory, Merchant, MerchantAlias, new_id, utcnow
from expense_tracker.services.transactions import classify_transaction


# (Pattern match, Canonical Display Name, Category Slug, Subcategory Slug)
MERCHANT_RULES = [
    # Group 1: Daily Micro-UPI Vendors & Tea Breaks
    (r"syed naseeruddin", "Syed Naseeruddin (Tea Stall)", "food", "tea-break"),
    (r"kings pan shop", "Kings Pan Shop", "food", "tea-break"),
    (r"md moin khan|md moiaz", "Md Moin Khan (Tea Stall)", "food", "tea-break"),
    (r"ruchivanam", "Ruchivanam Tiffins", "food", "restaurants"),
    (r"the bullet cafe", "The Bullet Cafe", "food", "tea-break"),

    # Group 2: Recurring Household & Supermarkets
    (r"sampoorna", "Sampoorna Supermarket", "food", "groceries"),
    (r"ratnadeep", "Ratnadeep Supermarket", "food", "groceries"),
    (r"blinkit", "Blinkit", "food", "groceries"),
    (r"ramdev stationery", "Ramdev Stationery Store", "shopping", "general"),

    # Group 3: Dining, Cafes & Food Courts
    (r"synergine", "Synergine Food Court", "food", "restaurants"),
    (r"aroha innovations", "Aroha Innovations", "food", "restaurants"),
    (r"rrr liquor", "RRR Liquor Mart", "food", "beverages"),
    (r"kopi desa", "Kopi Desa", "food", "restaurants"),
    (r"zomoz kompally", "Zomoz Kompally", "food", "restaurants"),
    (r"crispy days", "Crispy Days", "food", "restaurants"),

    # Group 4: Recurring Fuel Stations
    (r"cyberabad filling", "Cyberabad Filling Station", "fuel", "petrol"),
    (r"s s filling", "S S Filling Station", "fuel", "petrol"),
    (r"excel energy", "Excel Energy Mart", "fuel", "petrol"),
    (r"iocl govt special", "IOCL Petrol Pump (Govt Hospital)", "fuel", "petrol"),

    # Group 5: Home, Maintenance & Society Dues
    (r"nobroker", "NoBrokerHood Maintenance", "home", "maintenance"),
    (r"sabirali", "Sabir Ali (Home Maintenance)", "home", "repairs"),
    (r"kamal singh", "Kamal Singh (Home Painting/Repairs)", "home", "repairs"),
    (r"aparna kanopy", "Aparna Kanopy Marigold Maintenance", "home", "maintenance"),

    # Group 6: Personal Care, Healthcare & Family
    (r"anil kumar singh", "Anil Kumar Singh (Dad)", "family", "dad"),
    (r"pony salon", "Pony Salons", "personal-care", "salon-haircut"),
    (r"apollo pharmacy", "Apollo Pharmacy", "healthcare", "pharmacy"),

    # Group 7: Entertainment & Cinema
    (r"bigtree|bookmyshow", "BookMyShow", "entertainment", "movies"),
    (r"aparna cinema|cinepolis", "Cinépolis / Aparna Cinemas", "entertainment", "movies"),
    (r"amb cinema", "AMB Cinemas", "entertainment", "movies"),
]


def apply_groups_1_7(*, apply: bool = False) -> None:
    import re
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        cats = {c.slug: c for c in session.scalars(select(Category)).all()}
        subcats_by_cat: dict[str, dict[str, Subcategory]] = {}
        for c in cats.values():
            subcats_by_cat[c.slug] = {s.slug: s for s in c.subcategories}

        txs = session.scalars(
            select(Transaction).where(
                Transaction.transaction_type != "not_a_transaction",
                Transaction.excludes_from_spending == False,
                Transaction.is_transfer == False,
            )
        ).all()

        matched_count = 0
        merchant_entities: dict[str, Merchant] = {}

        for pattern, clean_name, cat_slug, subcat_slug in MERCHANT_RULES:
            regex = re.compile(pattern, re.I)
            cat_obj = cats.get(cat_slug)
            subcat_obj = subcats_by_cat.get(cat_slug, {}).get(subcat_slug) if cat_slug else None

            # Get or create Merchant
            norm_key = clean_name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
            merchant = session.scalar(select(Merchant).where(Merchant.normalized_key == norm_key))
            if not merchant:
                merchant = Merchant(
                    id=new_id(),
                    display_name=clean_name,
                    canonical_name=clean_name,
                    normalized_key=norm_key,
                    category_hint=f"{cat_obj.name if cat_obj else ''}/{subcat_obj.name if subcat_obj else ''}",
                    default_category_id=cat_obj.id if cat_obj else None,
                    default_subcategory_id=subcat_obj.id if subcat_obj else None,
                )
                if apply:
                    session.add(merchant)
                    session.flush()
            else:
                if apply:
                    merchant.display_name = clean_name
                    merchant.canonical_name = clean_name
                    if cat_obj:
                        merchant.default_category_id = cat_obj.id
                    if subcat_obj:
                        merchant.default_subcategory_id = subcat_obj.id
            merchant_entities[clean_name] = merchant

            for t in txs:
                blob = f"{t.merchant_raw or ''} {t.merchant_normalized or ''} {t.description or ''}"
                if regex.search(blob):
                    matched_count += 1
                    if apply:
                        t.merchant_normalized = clean_name
                        t.merchant_entity_id = merchant.id
                        if cat_obj:
                            classify_transaction(
                                session,
                                t.id,
                                category_id=cat_obj.id,
                                subcategory_id=subcat_obj.id if subcat_obj else None,
                            )

        if apply:
            session.commit()
            print(f"Successfully normalized and categorized {matched_count} transactions across groups 1-7!")
        else:
            print(f"[DRY-RUN] Would normalize and categorize {matched_count} transactions across groups 1-7. Pass --apply to persist.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize and classify groups 1-7.")
    parser.add_argument("--apply", action="store_true", help="Apply changes.")
    args = parser.parse_args()
    apply_groups_1_7(apply=args.apply)
