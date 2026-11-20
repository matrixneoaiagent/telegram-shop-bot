from __future__ import annotations

import csv
import io

from bot import services


def read_csv(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


async def test_csv_header_and_row(shop, make_order):
    order = await make_order(quantity=2)
    rows = read_csv(await services.export_orders_csv(shop["db"]))
    assert rows[0] == [
        "order_number",
        "created_at",
        "status",
        "customer_name",
        "phone",
        "address",
        "payment_method",
        "total",
        "currency",
        "tracking_number",
        "items",
    ]
    assert rows[1][0] == order["order_number"]
    assert rows[1][2] == "new"
    assert rows[1][3] == "Ana Popescu"
    assert rows[1][7] == "49.00"
    assert rows[1][8] == "USD"
    assert rows[1][9] == ""
    assert rows[1][10] == "2x Smart Mug"


async def test_csv_includes_tracking_and_status(shop, make_order):
    order = await make_order()
    await services.set_order_status(shop["db"], order["order_number"], "paid")
    await services.set_tracking(shop["db"], order["order_number"], "TRACK-99")
    rows = read_csv(await services.export_orders_csv(shop["db"]))
    assert rows[1][2] == "shipped"
    assert rows[1][9] == "TRACK-99"


async def test_csv_status_filter(shop, make_order):
    first = await make_order()
    second = await make_order(product=shop["cable"])
    await services.set_order_status(shop["db"], first["order_number"], "paid")
    rows = read_csv(await services.export_orders_csv(shop["db"], status="paid"))
    assert len(rows) == 2
    assert rows[1][0] == first["order_number"]
    assert rows[1][0] != second["order_number"]


async def test_csv_orders_are_chronological(shop, make_order):
    first = await make_order()
    second = await make_order(product=shop["cable"])
    rows = read_csv(await services.export_orders_csv(shop["db"]))
    assert [rows[1][0], rows[2][0]] == [first["order_number"], second["order_number"]]


async def test_csv_quotes_commas_and_newlines(shop, order_factory):
    order = await order_factory(address='12 Main St, Apt "4"\nChisinau')
    rows = read_csv(await services.export_orders_csv(shop["db"]))
    assert rows[1][5] == '12 Main St, Apt "4" Chisinau'
    assert rows[1][0] == order["order_number"]


async def test_csv_multiple_items(shop, order_factory):
    await order_factory(items=[(shop["mug"]["id"], 1), (shop["cable"]["id"], 3)])
    rows = read_csv(await services.export_orders_csv(shop["db"]))
    assert rows[1][10] == "1x Smart Mug; 3x USB-C Cable"


async def test_csv_empty_shop(shop):
    rows = read_csv(await services.export_orders_csv(shop["db"]))
    assert len(rows) == 1


async def test_csv_has_no_bom(shop, make_order):
    await make_order()
    text = await services.export_orders_csv(shop["db"])
    assert not text.startswith("\ufeff")
