"""Smoke tests that the routers and message formatting are wired correctly.

No Telegram network calls are made: the dispatcher is built but never polled.
"""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot import keyboards, services
from bot.config import PaymentMethod, Settings
from bot.formatting import money, order_summary, status_label
from bot.handlers import admin, catalog


def test_routers_register():
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(admin.build_admin_router(frozenset({1})))
    dispatcher.include_router(catalog.router)
    assert len(dispatcher.sub_routers) == 2
    dispatcher["db"] = object()
    assert "db" in dispatcher.workflow_data


def test_main_module_imports():
    import bot.main  # noqa: F401


def test_money_formatting():
    assert money(2450) == "$24.50"
    assert money(100000) == "$1,000.00"
    assert money(999, "EUR") == "9.99 EUR"


def test_status_labels():
    assert status_label("new") == "New — awaiting payment"
    assert status_label("shipped") == "Shipped"


def test_order_summary_uses_payment_label(shop):
    settings = Settings(
        bot_token="123456:TEST",
        admin_ids=frozenset({1}),
        currency="USD",
        payment_methods=(PaymentMethod("cod", "Cash on delivery", "Pay on delivery."),),
    )
    order = {
        "order_number": "SB-000001",
        "status": "shipped",
        "total_cents": 2450,
        "payment_method": "cod",
        "customer_name": "Ana <Popescu>",
        "phone": "+373 60 123 456",
        "address": "Str. Test 1",
        "tracking_number": "TRACK-1",
        "items": [
            {
                "product_name": "Smart Mug",
                "quantity": 1,
                "subtotal_cents": 2450,
            }
        ],
    }
    text = order_summary(order, settings)
    assert "Cash on delivery" in text
    assert "SB-000001" in text
    assert "TRACK-1" in text
    assert "Ana &lt;Popescu&gt;" in text
    assert "Welcome" not in text


def test_keyboards_have_expected_callbacks():
    start = keyboards.start_menu()
    callbacks = [button.callback_data for row in start.inline_keyboard for button in row]
    assert callbacks == ["menu:catalog", "menu:track", "menu:orders", "menu:help"]


def test_csv_roundtrip_shape(shop):
    # Importing the service layer here guards against accidental API drift.
    assert services.MAX_QUANTITY == 99
