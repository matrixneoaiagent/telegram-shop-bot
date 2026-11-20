from __future__ import annotations

import pytest
import pytest_asyncio

from bot import services
from bot.db import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "shop-test.db"))
    await database.connect()
    await database.init()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def shop(db):
    category_id = await services.ensure_category(db, "Gadgets")
    mug = await services.add_product(
        db,
        category_id=category_id,
        name="Smart Mug",
        description="Keeps coffee warm.",
        price_cents=2450,
        stock=5,
    )
    cable = await services.add_product(
        db,
        category_id=category_id,
        name="USB-C Cable",
        description="2 m braided cable.",
        price_cents=999,
        stock=10,
    )
    return {"db": db, "category_id": category_id, "mug": mug, "cable": cable}


async def place_order(db: Database, product: dict, quantity: int = 1, **overrides) -> dict:
    values = {
        "user_id": 1001,
        "username": "buyer",
        "customer_name": "Ana Popescu",
        "phone": "+373 60 123 456",
        "address": "Str. Maria Cebotari 12, Chisinau",
        "payment_method": "cod",
        "items": [(product["id"], quantity)],
        "currency": "USD",
    }
    values.update(overrides)
    return await services.create_order(db, **values)


@pytest.fixture
def make_order(shop):
    async def _make(product=None, quantity: int = 1, **overrides) -> dict:
        return await place_order(shop["db"], product or shop["mug"], quantity=quantity, **overrides)

    return _make


@pytest.fixture
def order_factory(shop):
    async def _place(product=None, quantity: int = 1, **overrides) -> dict:
        return await place_order(shop["db"], product or shop["mug"], quantity=quantity, **overrides)

    return _place
