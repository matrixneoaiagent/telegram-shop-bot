from __future__ import annotations

import pytest

from bot import services


async def test_tracking_marks_paid_order_shipped(shop, make_order):
    order = await make_order()
    await services.set_order_status(shop["db"], order["order_number"], "paid")
    updated = await services.set_tracking(shop["db"], order["order_number"], "TRACK-123456")
    assert updated["status"] == "shipped"
    assert updated["tracking_number"] == "TRACK-123456"
    assert updated["events"][-1]["comment"] == "Tracking: TRACK-123456"


async def test_tracking_requires_paid_order(shop, make_order):
    order = await make_order()
    with pytest.raises(services.InvalidTransition):
        await services.set_tracking(shop["db"], order["order_number"], "TRACK-1")


async def test_tracking_can_be_updated_after_shipping(shop, make_order):
    order = await make_order()
    await services.set_order_status(shop["db"], order["order_number"], "paid")
    await services.set_tracking(shop["db"], order["order_number"], "TRACK-1")
    updated = await services.set_tracking(shop["db"], order["order_number"], "TRACK-2")
    assert updated["status"] == "shipped"
    assert updated["tracking_number"] == "TRACK-2"


@pytest.mark.parametrize("tracking", ["", "x", "a" * 65])
async def test_tracking_number_is_validated(shop, make_order, tracking):
    order = await make_order()
    await services.set_order_status(shop["db"], order["order_number"], "paid")
    with pytest.raises(services.ValidationError):
        await services.set_tracking(shop["db"], order["order_number"], tracking)


async def test_buyer_can_lookup_own_order(shop, make_order):
    order = await make_order(user_id=777)
    found = await services.get_user_order(shop["db"], order["order_number"], 777)
    assert found is not None
    assert found["order_number"] == order["order_number"]


async def test_other_buyer_cannot_lookup_order(shop, make_order):
    order = await make_order(user_id=777)
    assert await services.get_user_order(shop["db"], order["order_number"], 888) is None


async def test_tracking_lookup_normalizes_number(shop, make_order):
    order = await make_order(user_id=777)
    found = await services.get_user_order(shop["db"], f"  {order['order_number'].lower()} ", 777)
    assert found is not None


async def test_admin_lookup_returns_customer_and_events(shop, make_order):
    order = await make_order(user_id=777)
    await services.set_order_status(shop["db"], order["order_number"], "confirmed")
    found = await services.get_order(shop["db"], order["order_number"])
    assert found["customer_name"] == "Ana Popescu"
    assert found["phone"] == "+373 60 123 456"
    assert [event["status"] for event in found["events"]] == ["new", "confirmed"]


async def test_status_change_notifies_flow_data(shop, make_order):
    order = await make_order(user_id=777)
    updated = await services.set_order_status(shop["db"], order["order_number"], "paid")
    assert updated["user_id"] == 777
    assert updated["status"] == "paid"
