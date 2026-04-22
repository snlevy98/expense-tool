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
    ("Debt",            "#ef4444", ["Car Loan", "Taxes (federal)", "Taxes (state)", "Other"]),
    ("Robinhood",       "#10b981", ["Preslie", "Sellars"]),
    ("Entertainment",   "#8b5cf6", ["Social", "Self", "Subscriptions"]),
    ("Groceries",       "#f59e0b", ["Grocs"]),
    ("Gifts/Donations", "#ec4899", ["Gifts", "Charity", "Other"]),
    ("Health",          "#06b6d4", ["Health"]),
    ("Home",            "#84cc16", ["Home"]),
    ("Insurance",       "#6366f1", ["Car", "Renters", "Life", "Pet"]),
    ("Wazo",            "#f97316", ["Vet/medical", "Grooming"]),
    ("Tesla",           "#14b8a6", ["Charging/NTTA/Self-Driving"]),
    ("Travel",          "#a855f7", ["Misc", "Duke/Kayla", "Cancun", "Germany Deposit"]),
    ("Rent/Utilities",  "#3b82f6", ["Rent", "Electricity", "Internet"]),
    ("CR3 Expenses",    "#64748b", ["Amex", "VentureX", "CR3 Repayments"]),
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
