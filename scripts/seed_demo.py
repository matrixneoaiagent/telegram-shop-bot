"""Seed a demo catalog.

Usage:
    python -m scripts.seed_demo [--db shop.db]
"""

from __future__ import annotations

import argparse
import asyncio
import os

from bot import services
from bot.db import Database

PRODUCTS = [
    ("Home & Office", "Smart Mug", "Keeps your coffee at 55 °C for three hours.", 2450, 12),
    ("Home & Office", "Desk Lamp", "Warm LED lamp with a USB-C port.", 3900, 8),
    ("Accessories", "USB-C Cable", "2 m braided charging cable, 100 W.", 999, 40),
    ("Accessories", "Laptop Sleeve", "14-inch felt sleeve with a magnetic clasp.", 2900, 15),
    ("Accessories", "Power Bank", "10 000 mAh, 20 W USB-C PD.", 4500, 3),
]


async def seed(db_path: str) -> None:
    db = Database(db_path)
    await db.connect()
    await db.init()
    try:
        for category_name, name, description, price_cents, stock in PRODUCTS:
            existing = await db.fetchone("SELECT id FROM products WHERE name = ?", (name,))
            if existing:
                print(f"skip  {name} (already exists)")
                continue
            category_id = await services.ensure_category(db, category_name)
            product = await services.add_product(
                db,
                category_id=category_id,
                name=name,
                description=description,
                price_cents=price_cents,
                stock=stock,
            )
            print(f"added #{product['id']} {name} — {price_cents / 100:.2f} USD")
        print(f"done: {db_path}")
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the shop database with demo products")
    parser.add_argument("--db", default=os.environ.get("DB_PATH", "shop.db"))
    args = parser.parse_args()
    asyncio.run(seed(args.db))


if __name__ == "__main__":
    main()
