"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_PAYMENT_METHODS = (
    ("cod", "Cash on delivery", "Pay in cash when your order is delivered."),
)

STATUSES = ("new", "confirmed", "paid", "shipped", "delivered", "cancelled")


class ConfigError(ValueError):
    """Raised when the environment is missing required values."""


@dataclass(frozen=True)
class PaymentMethod:
    key: str
    label: str
    instructions: str


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    db_path: str = "shop.db"
    shop_name: str = "My Shop"
    currency: str = "USD"
    payment_methods: tuple[PaymentMethod, ...] = field(default_factory=tuple)
    low_stock_threshold: int = 5

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        token = values.get("BOT_TOKEN", "").strip()
        if not token or ":" not in token:
            raise ConfigError("BOT_TOKEN is required and must look like '<id>:<secret>'")

        raw_admins = values.get("ADMIN_IDS", "").strip()
        try:
            admin_ids = frozenset(int(part) for part in raw_admins.split(",") if part.strip())
        except ValueError as exc:
            raise ConfigError(
                "ADMIN_IDS must be a comma-separated list of numeric user IDs"
            ) from exc
        if not admin_ids:
            raise ConfigError("ADMIN_IDS must contain at least one Telegram user ID")

        methods = parse_payment_methods(values.get("PAYMENT_METHODS", "").strip())
        if not methods:
            methods = tuple(PaymentMethod(*method) for method in DEFAULT_PAYMENT_METHODS)

        try:
            threshold = int(values.get("LOW_STOCK_THRESHOLD", "5"))
        except ValueError as exc:
            raise ConfigError("LOW_STOCK_THRESHOLD must be an integer") from exc
        if threshold < 0:
            raise ConfigError("LOW_STOCK_THRESHOLD must be >= 0")

        currency = values.get("SHOP_CURRENCY", "USD").strip().upper() or "USD"

        return cls(
            bot_token=token,
            admin_ids=admin_ids,
            db_path=values.get("DB_PATH", "shop.db").strip() or "shop.db",
            shop_name=values.get("SHOP_NAME", "My Shop").strip() or "My Shop",
            currency=currency,
            payment_methods=methods,
            low_stock_threshold=threshold,
        )


def parse_payment_methods(raw: str) -> tuple[PaymentMethod, ...]:
    """Parse ``key|Label|Instructions`` entries separated by ``;;``.

    Instructions may contain ``\\n`` escapes for line breaks.
    """
    if not raw:
        return ()
    methods: list[PaymentMethod] = []
    seen: set[str] = set()
    for chunk in raw.split(";;"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [part.strip() for part in chunk.split("|", 2)]
        if len(parts) != 3 or not all(parts):
            raise ConfigError(
                "PAYMENT_METHODS entries must look like 'key|Label|Instructions' separated by ';;'"
            )
        key, label, instructions = parts
        if key in seen:
            raise ConfigError(f"duplicate payment method key: {key}")
        seen.add(key)
        methods.append(PaymentMethod(key, label, instructions.replace("\\n", "\n")))
    return tuple(methods)
