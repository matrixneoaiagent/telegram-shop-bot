from __future__ import annotations

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import ConfigError, PaymentMethod, Settings


def test_settings_from_env_full():
    settings = Settings.from_env(
        {
            "BOT_TOKEN": "123456:TEST-TOKEN",
            "ADMIN_IDS": "42, 77",
            "DB_PATH": "/tmp/shop.db",
            "SHOP_NAME": "Neo Store",
            "SHOP_CURRENCY": "usd",
            "PAYMENT_METHODS": (
                "usdt|USDT (TRC20)|Send to TXYZ\\nThen send the hash;;cod|Cash|Pay on delivery"
            ),
            "LOW_STOCK_THRESHOLD": "3",
        }
    )
    assert settings.bot_token == "123456:TEST-TOKEN"
    assert settings.admin_ids == frozenset({42, 77})
    assert settings.db_path == "/tmp/shop.db"
    assert settings.shop_name == "Neo Store"
    assert settings.currency == "USD"
    assert settings.low_stock_threshold == 3
    assert settings.payment_methods == (
        PaymentMethod("usdt", "USDT (TRC20)", "Send to TXYZ\nThen send the hash"),
        PaymentMethod("cod", "Cash", "Pay on delivery"),
    )


def test_settings_defaults_to_cash_on_delivery():
    settings = Settings.from_env({"BOT_TOKEN": "1:SECRET", "ADMIN_IDS": "1"})
    assert settings.currency == "USD"
    assert settings.db_path == "shop.db"
    assert [method.key for method in settings.payment_methods] == ["cod"]


@pytest.mark.parametrize(
    "env",
    [
        {"ADMIN_IDS": "1"},
        {"BOT_TOKEN": "not-a-token", "ADMIN_IDS": "1"},
        {"BOT_TOKEN": "1:SECRET"},
        {"BOT_TOKEN": "1:SECRET", "ADMIN_IDS": "abc"},
        {"BOT_TOKEN": "1:SECRET", "ADMIN_IDS": "1", "LOW_STOCK_THRESHOLD": "x"},
    ],
)
def test_settings_rejects_bad_env(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_payment_methods_reject_duplicates():
    with pytest.raises(ConfigError):
        Settings.from_env(
            {
                "BOT_TOKEN": "1:SECRET",
                "ADMIN_IDS": "1",
                "PAYMENT_METHODS": "cod|Cash|Pay;;cod|Cash again|Pay",
            }
        )


def test_payment_methods_reject_malformed_entry():
    with pytest.raises(ConfigError):
        Settings.from_env(
            {"BOT_TOKEN": "1:SECRET", "ADMIN_IDS": "1", "PAYMENT_METHODS": "cod|Cash"}
        )


async def test_fake_bot_token_needs_no_network():
    settings = Settings.from_env({"BOT_TOKEN": "123456:TEST", "ADMIN_IDS": "1"})
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        assert bot.token == "123456:TEST"
        assert bot.default.parse_mode == ParseMode.HTML
    finally:
        await bot.session.close()
