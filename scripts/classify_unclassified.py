"""Classify remaining unclassified transactions using verified merchant and context rules."""

from __future__ import annotations

import argparse
import re
import warnings
from bs4 import XMLParsedAsHTMLWarning
from sqlalchemy import select
from sqlalchemy.orm import Session

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from mymonee.db.session import get_session_factory
from mymonee.db.models import Transaction, Email, Category, Subcategory
from mymonee.parsers.extract import html_to_text
from mymonee.services.transactions import classify_transaction


def get_classification_map(session: Session) -> dict[str, tuple[str, str | None]]:
    cats = {c.slug: c for c in session.scalars(select(Category)).all()}
    subcats_by_cat: dict[str, dict[str, Subcategory]] = {}
    for c in cats.values():
        subcats_by_cat[c.slug] = {s.slug: s for s in c.subcategories}

    # Fetch active unclassified transactions
    txs = session.scalars(
        select(Transaction).where(
            (Transaction.category_id.is_(None)) | (Transaction.needs_review == True),
            Transaction.transaction_type != "not_a_transaction",
            Transaction.excludes_from_spending == False,
        )
    ).all()

    classifications: dict[str, tuple[str, str | None]] = {}

    for t in txs:
        email = session.get(Email, t.source_email_id) if t.source_email_id else None
        subj = email.subject if email else ""
        body = html_to_text(email.body_html or email.body_text or "")[:800] if email else ""
        body_clean = re.sub(r"call our 24-hour.*|if you have not made this transaction.*|toll free.*|partners never ask.*", "", body, flags=re.I)
        blob = f"{t.description or ''} {subj} {body_clean} {t.merchant_raw or ''} {t.merchant_normalized or ''}"

        c_slug = None
        s_slug = None

        # 1. Loans / Home
        if "63135" in str(t.amount) or "Standard Chartered" in blob or "Home Loan" in blob:
            c_slug, s_slug = "loans", "home"
        # 2. Car Loan / SBI RASMEC
        elif "32720" in str(t.amount) or "RASMEC" in blob or "SBI Car Loan" in blob:
            c_slug, s_slug = "loans", "car"
        # 3. Entertainment / Movies
        elif re.search(r"bigtree|bookmyshow|cinema|pvr|inox|cinepolis", blob, re.I):
            c_slug, s_slug = "entertainment", "movies"
        # 4. Entertainment / Games
        elif re.search(r"steam|playstation|xbox|nintendo|olympia", blob, re.I):
            c_slug, s_slug = "entertainment", "games"
        # 5. Food / Food Delivery
        elif re.search(r"swiggy|zomato|eatclub|faasos|mcdonald|domino|burger king", blob, re.I):
            c_slug, s_slug = "food", "food-delivery"
        # 6. Food / Groceries
        elif re.search(r"zepto|bigbasket|blinkit|instamart|ratnadeep|sampoorna|nature.?s basket|dunzo", blob, re.I):
            c_slug, s_slug = "food", "groceries"
        # 7. Food / Cafe
        elif re.search(r"blue tokai|flurys|starbucks|third wave|costa coffee", blob, re.I):
            c_slug, s_slug = "food", "cafe"
        # 8. Food / Restaurants & Dining
        elif re.search(r"california burrito|ruchivanam|kopi desa|new town|bombay gour|synergine|s\.karachi|dil kush|frangos|zomoz|olive mitha|baan phadthai|shraddha restaurant|varahi|seasons xprs|indiana bakery|tiffin|restaurant|dining|kitchen|diner|baker", blob, re.I):
            c_slug, s_slug = "food", "restaurants"
        # 9. Shopping / Online Marketplace
        elif re.search(r"amazon|flipkart|myntra|ajio|meesho|decathlon|ikea|caratlane|ishopchangi", blob, re.I):
            c_slug, s_slug = "shopping", "online-marketplace"
        # 10. Subscriptions / Software & AI
        elif re.search(r"cursor|openai|chatgpt|github|apple\.com/bill|itunes|google india|google cloud|keyslo|microsoft", blob, re.I):
            c_slug, s_slug = "subscriptions", "software"
        # 11. Subscriptions / DTH
        elif re.search(r"tata play|dth recharge|sun direct|dish tv", blob, re.I):
            c_slug, s_slug = "subscriptions", "dth"
        # 12. Utilities / Internet
        elif re.search(r"act fibernet|broadband|actcorp|airtel broadband|jio fiber|aponline", blob, re.I):
            c_slug, s_slug = "utilities", "internet"
        # 13. Utilities / Mobile
        elif re.search(r"airtel mobile|jio prepaid|jio postpaid|mahurakalan|vodafone|vi\b|mobile recharge", blob, re.I):
            c_slug, s_slug = "utilities", "mobile"
        # 14. Utilities / Gas
        elif re.search(r"green gas|bhagyanagar gas|indane|hp gas|bharat gas", blob, re.I):
            c_slug, s_slug = "utilities", "gas"
        # 15. Travel / Cab
        elif re.search(r"uber|ola|rapido|kolanidi malyadri", blob, re.I):
            c_slug, s_slug = "travel", "cab"
        # 16. Travel / Transit
        elif re.search(r"irctc|indian railways|uts\b|railway", blob, re.I):
            c_slug, s_slug = "travel", "transit"
        # 17. Travel / Flights
        elif re.search(r"indigo|ixigo|flight|air india|airline|goibibo|makemytrip", blob, re.I):
            c_slug, s_slug = "travel", "flights"
        # 18. Fuel / Petrol
        elif re.search(r"fuel|petrol|hpcl|bpcl|iocl|indian oil|shell|jayabheri filling|excel energy|coco hitec|vijay krishna filling", blob, re.I):
            c_slug, s_slug = "fuel", "petrol"
        # 19. Healthcare / Pharmacy & Labs
        elif re.search(r"apollo pharmacy|1mg|pharmeasy|netmeds|medplus", blob, re.I):
            c_slug, s_slug = "healthcare", "pharmacy"
        # 20. Healthcare / Hospital & Clinic
        elif re.search(r"hospital|clinic|doctor|dentist", blob, re.I):
            c_slug, s_slug = "healthcare", "clinic"
        # 21. Personal Care / Salon
        elif re.search(r"naturals|salon|haircut|spa|grooming", blob, re.I):
            c_slug, s_slug = "personal-care", "salon-haircut"
        # 22. Car / FASTag
        elif re.search(r"fastag|nhai|toll plaza", blob, re.I):
            c_slug, s_slug = "car", "fastag"
        # 23. Car / Maintenance
        elif re.search(r"auto care|automobile|v s n|sai siri|car service|car repair|honda service", blob, re.I):
            c_slug, s_slug = "car", "maintainence"
        # 24. Home / Maintenance
        elif re.search(r"nobroker|maintenance dues|society maintenance", blob, re.I):
            c_slug, s_slug = "home", "maintenance"
        # 25. Education / School
        elif re.search(r"abhaya|school fee|term fee|tuition|qfix", blob, re.I):
            c_slug, s_slug = "education", "tuition"
        # 26. Family
        elif re.search(r"anil kumar|dad", blob, re.I):
            c_slug, s_slug = "family", "dad"
        # 27. Food / Tea Break
        elif re.search(r"pan shop|tea stall|naseeruddin|moin khan|bullet cafe", blob, re.I):
            c_slug, s_slug = "food", "tea-break"

        if c_slug and c_slug in cats:
            cat_id = cats[c_slug].id
            subcat_id = None
            if s_slug and s_slug in subcats_by_cat[c_slug]:
                subcat_id = subcats_by_cat[c_slug][s_slug].id
            classifications[t.id] = (cat_id, subcat_id)

    return classifications


def apply_classifications(*, apply: bool = False) -> None:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        class_map = get_classification_map(session)
        print(f"Total Transactions Identified for Classification: {len(class_map)}")

        if apply:
            for tx_id, (cat_id, subcat_id) in class_map.items():
                classify_transaction(
                    session,
                    tx_id,
                    category_id=cat_id,
                    subcategory_id=subcat_id,
                )
            session.commit()
            print(f"Successfully classified and verified {len(class_map)} transactions!")
        else:
            print("[DRY-RUN] Pass --apply to persist classifications.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify unclassified transactions.")
    parser.add_argument("--apply", action="store_true", help="Apply classifications.")
    args = parser.parse_args()
    apply_classifications(apply=args.apply)
