from __future__ import annotations

import sqlite3

import pytest

from bot import services
from bot.db import SCHEMA_VERSION


async def test_schema_creates_expected_tables(db):
    rows = await db.fetchall("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    tables = {row["name"] for row in rows}
    assert {
        "categories",
        "products",
        "orders",
        "order_items",
        "order_events",
        "schema_meta",
    } <= tables
    version = await db.fetchone("SELECT value FROM schema_meta WHERE key = 'version'")
    assert version["value"] == SCHEMA_VERSION


async def test_schema_init_is_idempotent(db):
    await db.init()
    count = await db.fetchone("SELECT COUNT(*) AS count FROM schema_meta")
    assert count["count"] == 1


async def test_category_names_are_unique_case_insensitive(db):
    first = await services.ensure_category(db, "Gadgets")
    second = await services.ensure_category(db, "  gadgets ")
    assert first == second
    categories = await services.list_categories(db)
    assert len(categories) == 1
    assert categories[0]["name"] == "Gadgets"


async def test_product_create_and_read(shop):
    product = await services.get_product(shop["db"], shop["mug"]["id"])
    assert product["name"] == "Smart Mug"
    assert product["price_cents"] == 2450
    assert product["stock"] == 5
    assert product["category_name"] == "Gadgets"
    assert product["is_active"] == 1


async def test_product_requires_existing_category(db):
    with pytest.raises(services.NotFound):
        await services.add_product(db, category_id=999, name="Ghost", price_cents=100, stock=1)


async def test_update_product_fields(shop):
    updated = await services.update_product(
        shop["db"], shop["mug"]["id"], name="  Smarter Mug  ", price_cents=2999, stock=7
    )
    assert updated["name"] == "Smarter Mug"
    assert updated["price_cents"] == 2999
    assert updated["stock"] == 7


@pytest.mark.parametrize(
    "payload",
    [
        {"price_cents": -1},
        {"stock": -1},
        {"name": "x"},
        {"nope": 1},
    ],
)
async def test_update_product_validates(shop, payload):
    with pytest.raises(services.ValidationError):
        await services.update_product(shop["db"], shop["mug"]["id"], **payload)


async def test_parse_price():
    assert services.parse_price("12.50") == 1250
    assert services.parse_price("$1,299.99") == 129999
    assert services.parse_price("0") == 0
    for bad in ("", "abc", "1.999", "-2"):
        with pytest.raises(services.ValidationError):
            services.parse_price(bad)


async def test_foreign_keys_are_enforced(shop):
    with pytest.raises(sqlite3.IntegrityError):
        await shop["db"].execute(
            "INSERT INTO products(category_id, name, price_cents, stock, created_at, updated_at) "
            "VALUES(999, 'Orphan', 100, 1, '2026-01-01', '2026-01-01')"
        )
