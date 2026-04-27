"""
Reset + reseed script: wipes all existing categories and subcategories,
then creates the new ones defined in seed_categories.SEED.

WARNING: This nulls out category_id and subcategory_id on ALL transactions.
Run once after deploying the new category list.

Usage:
    cd backend
    python reset_and_seed_categories.py
"""

import asyncio
import uuid

from sqlalchemy import delete, update

from app.db.session import AsyncSessionLocal
from app.models.budget import Budget
from app.models.budget_default import BudgetDefault
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction
from seed_categories import SEED


async def reset_and_seed() -> None:
    async with AsyncSessionLocal() as db:
        print("Step 1: Clearing category/subcategory references from all transactions…")
        result = await db.execute(
            update(Transaction)
            .values(category_id=None, subcategory_id=None,
                    ai_suggested_category_id=None, ai_suggested_subcategory_id=None)
        )
        print(f"  Updated {result.rowcount} transaction rows.")

        print("Step 2: Deleting all budgets and budget defaults…")
        bd_result = await db.execute(delete(BudgetDefault))
        print(f"  Deleted {bd_result.rowcount} budget defaults.")
        b_result = await db.execute(delete(Budget))
        print(f"  Deleted {b_result.rowcount} budgets.")

        print("Step 3: Deleting all subcategories…")
        sub_result = await db.execute(delete(Subcategory))
        print(f"  Deleted {sub_result.rowcount} subcategories.")

        print("Step 4: Deleting all categories…")
        cat_result = await db.execute(delete(Category))
        print(f"  Deleted {cat_result.rowcount} categories.")

        await db.flush()

        print("Step 5: Seeding new categories and subcategories…")
        created_cats = 0
        created_subs = 0

        for cat_name, color, subcategory_names in SEED:
            category = Category(id=uuid.uuid4(), name=cat_name, color=color)
            db.add(category)
            await db.flush()
            print(f"  + {cat_name}  ({color})")
            created_cats += 1

            for sub_name in subcategory_names:
                db.add(Subcategory(
                    id=uuid.uuid4(),
                    category_id=category.id,
                    name=sub_name,
                ))
                print(f"      + {sub_name}")
                created_subs += 1

        await db.commit()
        print(f"\nDone. Created {created_cats} categories and {created_subs} subcategories.")
        print("All transaction category assignments have been cleared — use the Categorize page to reassign.")


if __name__ == "__main__":
    asyncio.run(reset_and_seed())
