"""Scripted, offline walkthrough of the shop flow.

This runs against a throw-away SQLite database and exercises the same service
functions the Telegram handlers call. It never contacts Telegram, which makes it
safe to run in CI, in a demo, or in front of a client.

Usage:
    python -m scripts.demo_walkthrough
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from bot import services
from bot.config import PaymentMethod, Settings
from bot.db import Database
from bot.formatting import money, order_summary, payment_label, status_label

DEMO_SETTINGS = Settings(
    bot_token="123456:DEMO-TOKEN",
    admin_ids=frozenset({9001}),
    shop_name="Neo Gadgets",
    currency="USD",
    payment_methods=(
        PaymentMethod(
            "usdt_trc20",
            "USDT (TRC20)",
            "Send the exact amount in USDT (TRC20) to TXYZ...DEMO\n"
            "Then send the transaction hash in this chat.",
        ),
        PaymentMethod("cod", "Cash on delivery", "Pay in cash when the courier arrives."),
    ),
)


def heading(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        db = Database(str(Path(directory) / "demo.db"))
        await db.connect()
        await db.init()
        try:
            heading("1. Seed catalog")
            home = await services.ensure_category(db, "Home & Office")
            accessories = await services.ensure_category(db, "Accessories")
            mug = await services.add_product(
                db,
                category_id=home,
                name="Smart Mug",
                description="Keeps coffee at 55 °C for three hours.",
                price_cents=2450,
                stock=12,
            )
            cable = await services.add_product(
                db,
                category_id=accessories,
                name="USB-C Cable",
                description="2 m braided cable, 100 W.",
                price_cents=999,
                stock=40,
            )
            for category in await services.list_categories(db):
                print(f"[category] {category['name']} ({category['product_count']} products)")
                for product in await services.list_products(db, category["id"]):
                    print(
                        f"  #{product['id']} {product['name']} — "
                        f"{money(product['price_cents'])} · stock {product['stock']}"
                    )

            heading("2. Customer checkout (name / phone / address / payment)")
            print("Customer: Ana Popescu · +373 60 123 456 · Str. Maria Cebotari 12, Chisinau")
            print("Cart: 2x Smart Mug, 1x USB-C Cable")
            order = await services.create_order(
                db,
                user_id=777,
                username="ana_demo",
                customer_name="Ana Popescu",
                phone="+373 60 123 456",
                address="Str. Maria Cebotari 12, Chisinau",
                payment_method="usdt_trc20",
                items=[(mug["id"], 2), (cable["id"], 1)],
            )
            print(f"\nOrder created: {order['order_number']}")
            print(order_summary(order, DEMO_SETTINGS))
            method = next(
                item
                for item in DEMO_SETTINGS.payment_methods
                if item.key == order["payment_method"]
            )
            print(f"\nPayment instructions ({payment_label(DEMO_SETTINGS, method.key)}):")
            print(method.instructions)

            heading("3. Admin confirms payment and ships")
            await services.set_order_status(db, order["order_number"], "paid", "USDT received")
            print(f"admin> /setstatus {order['order_number']} paid USDT received")
            order = await services.set_tracking(db, order["order_number"], "TRACK-2026-0042")
            print(f"admin> /tracking {order['order_number']} TRACK-2026-0042")
            print(f"status now: {status_label(order['status'])}")

            heading("4. Customer tracks the order")
            tracked = await services.get_user_order(db, order["order_number"], 777)
            print(order_summary(tracked, DEMO_SETTINGS))
            print("\nHistory:")
            for event in tracked["events"]:
                print(f"  {event['created_at']}  {event['status']}  {event['comment'] or ''}")

            heading("5. Another customer cannot see this order")
            other = await services.get_user_order(db, order["order_number"], 888)
            print(f"lookup as user 888 -> {other}")

            heading("6. Admin CSV export")
            print(await services.export_orders_csv(db))

            heading("7. Stats and low stock")
            stats = await services.shop_stats(db, low_stock_threshold=5)
            print(stats)
        finally:
            await db.close()
    print("\nDemo finished. No Telegram API calls were made.")


if __name__ == "__main__":
    asyncio.run(main())
