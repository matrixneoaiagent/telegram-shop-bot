from __future__ import annotations

import asyncio

import pytest

from bot import services


async def test_order_decrements_stock(shop, make_order):
    await make_order(quantity=2)
    product = await services.get_product(shop["db"], shop["mug"]["id"])
    assert product["stock"] == 3


async def test_insufficient_stock_rolls_back(shop, order_factory):
    with pytest.raises(services.OutOfStock) as excinfo:
        await order_factory(shop["mug"], quantity=6)
    assert excinfo.value.available == 5
    product = await services.get_product(shop["db"], shop["mug"]["id"])
    assert product["stock"] == 5
    count = await shop["db"].fetchone("SELECT COUNT(*) AS count FROM orders")
    assert count["count"] == 0


async def test_out_of_stock_product_cannot_be_ordered(shop, order_factory):
    await services.set_stock(shop["db"], shop["mug"]["id"], 0)
    with pytest.raises(services.OutOfStock):
        await order_factory(shop["mug"])
    count = await shop["db"].fetchone("SELECT COUNT(*) AS count FROM orders")
    assert count["count"] == 0


async def test_cancelling_restores_stock(shop, make_order):
    order = await make_order(quantity=3)
    await services.set_order_status(shop["db"], order["order_number"], "cancelled")
    product = await services.get_product(shop["db"], shop["mug"]["id"])
    assert product["stock"] == 5


async def test_cancelled_order_does_not_restore_twice(shop, make_order):
    order = await make_order(quantity=2)
    await services.set_order_status(shop["db"], order["order_number"], "cancelled")
    with pytest.raises(services.InvalidTransition):
        await services.set_order_status(shop["db"], order["order_number"], "cancelled")
    product = await services.get_product(shop["db"], shop["mug"]["id"])
    assert product["stock"] == 5


async def test_concurrent_buyers_cannot_oversell(shop, order_factory):
    await services.set_stock(shop["db"], shop["mug"]["id"], 1)
    results = await asyncio.gather(
        order_factory(shop["mug"], user_id=1),
        order_factory(shop["mug"], user_id=2),
        return_exceptions=True,
    )
    successes = [result for result in results if isinstance(result, dict)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], services.OutOfStock)
    product = await services.get_product(shop["db"], shop["mug"]["id"])
    assert product["stock"] == 0


async def test_hidden_product_cannot_be_ordered(shop, order_factory):
    await services.update_product(shop["db"], shop["mug"]["id"], is_active=False)
    with pytest.raises(services.NotFound):
        await order_factory(shop["mug"])


async def test_adjust_stock(shop):
    updated = await services.adjust_stock(shop["db"], shop["mug"]["id"], 4)
    assert updated["stock"] == 9
    updated = await services.adjust_stock(shop["db"], shop["mug"]["id"], -9)
    assert updated["stock"] == 0
    with pytest.raises(services.ValidationError):
        await services.adjust_stock(shop["db"], shop["mug"]["id"], -1)
