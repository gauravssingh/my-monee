"""Seed default category hierarchy for the dashboard."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from mymonee.db.models import Category, Subcategory, new_id

DEFAULT_CATEGORIES: list[tuple[str, list[str]]] = [
    ("Food", ["Food Delivery", "Restaurants", "Groceries", "Cafe"]),
    ("Shopping", ["General", "Electronics", "Apparel", "Online Marketplace"]),
    ("Travel", ["Flights", "Hotels", "Cab", "Transit"]),
    ("Fuel", ["Petrol", "Diesel", "EV Charging"]),
    ("Entertainment", ["Streaming", "Movies", "Events", "Games"]),
    ("Utilities", ["Electricity", "Water", "Internet", "Mobile", "Gas"]),
    ("Subscriptions", ["Software", "Membership", "News"]),
    ("Healthcare", ["Pharmacy", "Clinic", "Insurance"]),
    ("Education", ["Courses", "Books", "Tuition"]),
    ("Home", ["Rent", "Maintenance", "Furniture"]),
    ("Transfers", ["Own Account", "Credit Card Payment", "Investment"]),
    ("Income", ["Salary", "Refund", "Interest", "Other Income"]),
    ("Fees & Interest", ["Bank Fee", "EMI Interest", "Late Fee", "GST"]),
    ("Other", ["Uncategorized", "Cash Withdrawal"]),
]


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def seed_defaults(session: Session) -> None:
    existing = session.scalar(select(Category).limit(1))
    if existing:
        return

    for order, (cat_name, subs) in enumerate(DEFAULT_CATEGORIES):
        category = Category(
            id=new_id(),
            name=cat_name,
            slug=_slugify(cat_name),
            sort_order=order,
            is_system=True,
        )
        session.add(category)
        session.flush()
        for sub_order, sub_name in enumerate(subs):
            session.add(
                Subcategory(
                    id=new_id(),
                    category_id=category.id,
                    name=sub_name,
                    slug=_slugify(sub_name),
                    sort_order=sub_order,
                )
            )
