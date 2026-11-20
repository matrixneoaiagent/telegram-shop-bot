from __future__ import annotations

import pytest

from bot import services


async def test_order_number_and_totals(shop, make_order):
    order = await make_order(quantity=2)
    assert order["order_number"] == "SB-000001"
    assert order["total_cents"] == 4900
    assert order["status"] == "new"
    assert order["items"][0]["product_name"] == "Smart Mug"
    assert order["items"][0]["unit_price_cents"] == 2450
    assert order["items"][0]["subtotal_cents"] == 4900
    assert order["currency"] == "USD"


async def test_order_numbers_increment(shop, make_order):
    first = await make_order()
    second = await make_order(product=shop["cable"])
    assert first["order_number"] == "SB-000001"
    assert second["order_number"] == "SB-000002"


async def test_item_snapshot_survives_product_rename(shop, make_order):
    order = await make_order()
    await services.update_product(shop["db"], shop["mug"]["id"], name="Renamed Mug")
    reloaded = await services.get_order(shop["db"], order["order_number"])
    assert reloaded["items"][0]["product_name"] == "Smart Mug"


async def test_multi_item_order(shop, order_factory):
    order = await order_factory(items=[(shop["mug"]["id"], 1), (shop["cable"]["id"], 2)])
    assert order["total_cents"] == 2450 + 2 * 999
    assert len(order["items"]) == 2
    mug = await services.get_product(shop["db"], shop["mug"]["id"])
    cable = await services.get_product(shop["db"], shop["cable"]["id"])
    assert (mug["stock"], cable["stock"]) == (4, 8)


async def test_valid_status_transitions(shop, make_order):
    order = await make_order()
    number = order["order_number"]
    for status in ("confirmed", "paid", "shipped", "delivered"):
        order = await services.set_order_status(shop["db"], number, status)
        assert order["status"] == status
    assert [event["status"] for event in order["events"]] == [
        "new",
        "confirmed",
        "paid",
        "shipped",
        "delivered",
    ]


async def test_new_order_can_be_paid_directly(shop, make_order):
    order = await make_order()
    updated = await services.set_order_status(shop["db"], order["order_number"], "paid")
    assert updated["status"] == "paid"


async def test_invalid_transition_rejected(shop, make_order):
    order = await make_order()
    with pytest.raises(services.InvalidTransition):
        await services.set_order_status(shop["db"], order["order_number"], "shipped")


async def test_shipped_order_cannot_be_cancelled(shop, make_order):
    order = await make_order()
    await services.set_order_status(shop["db"], order["order_number"], "paid")
    await services.set_order_status(shop["db"], order["order_number"], "shipped")
    with pytest.raises(services.InvalidTransition):
        await services.set_order_status(shop["db"], order["order_number"], "cancelled")


async def test_unknown_status_rejected(shop, make_order):
    order = await make_order()
    with pytest.raises(services.ValidationError):
        await services.set_order_status(shop["db"], order["order_number"], "refunded")


async def test_status_comment_is_recorded(shop, make_order):
    order = await make_order()
    updated = await services.set_order_status(
        shop["db"], order["order_number"], "confirmed", "Payment link sent"
    )
    assert updated["events"][-1]["comment"] == "Payment link sent"


async def test_order_not_found(shop):
    with pytest.raises(services.NotFound):
        await services.set_order_status(shop["db"], "SB-999999", "paid")


@pytest.mark.parametrize(
    "customer",
    [
        {"customer_name": "A", "phone": "+373 60 123 456", "address": "Str. Test 1"},
        {"customer_name": "Ana", "phone": "abc", "address": "Str. Test 1"},
        {"customer_name": "Ana", "phone": "+373 60 123 456", "address": "x"},
    ],
)
async def test_invalid_customer_details_roll_back(shop, order_factory, customer):
    with pytest.raises(services.ValidationError):
        await order_factory(**customer)
    product = await services.get_product(shop["db"], shop["mug"]["id"])
    assert product["stock"] == 5
    count = await shop["db"].fetchone("SELECT COUNT(*) AS count FROM orders")
    assert count["count"] == 0


async def test_quantity_limits(shop, order_factory):
    with pytest.raises(services.ValidationError):
        await order_factory(quantity=0)
    with pytest.raises(services.ValidationError):
        await order_factory(quantity=100)


async def test_order_number_lookup_is_case_insensitive(shop, make_order):
    order = await make_order()
    found = await services.get_order(shop["db"], order["order_number"].lower())
    assert found["order_number"] == order["order_number"]
