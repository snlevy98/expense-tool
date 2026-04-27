"""
One-time seed script: creates categories and subcategories from the
predefined list below. Safe to re-run — skips any category/subcategory
whose name already exists.
"""

import asyncio
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.category import Category
from app.models.subcategory import Subcategory

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

SEED = [
    # Pastel palette spanning the full color wheel for clear visual distinction
    ("Debt",                "#FFB3B3", ["Car Loan", "Taxes (federal)", "Other"]),
    ("Necessary Expenses",  "#B8E8C4", ["Car Insurance", "Groceries", "Health/Medical", "Home Insurance", "Home Supplies", "Rent", "Utilities"]),
    ("For Funsies",         "#C8B4E8", ["Books", "Concerts", "DnD", "Gaming", "Fishies", "Hosting!", "Movies", "Outdoor activities", "Plant Dad", "Poker", "Sports", "Theatre", "Yoga", "Other"]),
    ("Everyday",            "#FECFA8", ["Baking", "Bars", "Beauty", "Clothes", "Coffee Shops", "Dates", "Food Delivery", "Home Booze", "Restaurants", "Other"]),
    ("Gifts",               "#FFB8D0", ["Gifts", "Donations", "Other"]),
    ("Home",                "#FFF0A0", ["Dry Cleaning", "Furnishings", "Maids", "Moving", "Other"]),
    ("Pets",                "#A8DCF0", ["Food", "Vet/medical", "Toys", "Supplies", "Other"]),
    ("Transportation",      "#B0D4B8", ["Charging", "Repairs", "Registration/license", "Public transit", "Other"]),
    ("Travel",              "#A4C4F4", ["Airfare", "Alcohol", "Entertainment", "Food", "Hotels", "Spa", "Transportation", "Other"]),
    ("Work",                "#B8D8E8", ["TV", "Misc. Purchases", "Travel Expenses", "Other"]),
    ("Investments",         "#D4B8D8", ["Robinhood - Preslie", "Robinhood - Sellars", "Life Insurance"]),
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        created_cats = 0
        created_subs = 0

        for cat_name, color, subcategory_names in SEED:
            # Find or create category
            result = await db.execute(
                select(Category).where(Category.name == cat_name)
            )
            category = result.scalar_one_or_none()

            if category is None:
                category = Category(id=uuid.uuid4(), name=cat_name, color=color)
                db.add(category)
                await db.flush()
                print(f"  + Category: {cat_name}")
                created_cats += 1
            else:
                print(f"  ~ Category already exists: {cat_name}")

            # Find or create each subcategory
            for sub_name in subcategory_names:
                sub_result = await db.execute(
                    select(Subcategory).where(
                        Subcategory.category_id == category.id,
                        Subcategory.name == sub_name,
                    )
                )
                sub = sub_result.scalar_one_or_none()

                if sub is None:
                    db.add(Subcategory(
                        id=uuid.uuid4(),
                        category_id=category.id,
                        name=sub_name,
                    ))
                    print(f"      + {sub_name}")
                    created_subs += 1
                else:
                    print(f"      ~ already exists: {sub_name}")

        await db.commit()
        print(f"\nDone. Created {created_cats} categories and {created_subs} subcategories.")


if __name__ == "__main__":
    asyncio.run(seed())
