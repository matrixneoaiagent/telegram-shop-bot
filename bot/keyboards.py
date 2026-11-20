"""Inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import PaymentMethod


def start_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Catalog", callback_data="menu:catalog")],
            [
                InlineKeyboardButton(text="📦 Track order", callback_data="menu:track"),
                InlineKeyboardButton(text="🧾 My orders", callback_data="menu:orders"),
            ],
            [InlineKeyboardButton(text="ℹ️ Help", callback_data="menu:help")],
        ]
    )


def categories(categories: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item['name']} ({item['product_count']})",
                callback_data=f"cat:{item['id']}",
            )
        ]
        for item in categories
    ]
    rows.append([InlineKeyboardButton(text="« Menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def products(products: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for item in products:
        stock = " · out of stock" if item["stock"] <= 0 else f" · {item['stock']} left"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{item['name']} — {item['price_cents'] / 100:.2f}{stock}",
                    callback_data=f"prod:{item['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="« Categories", callback_data="menu:catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product(product: dict) -> InlineKeyboardMarkup:
    rows = []
    if product["stock"] > 0:
        rows.append([InlineKeyboardButton(text="🛒 Buy now", callback_data=f"buy:{product['id']}")])
    rows.append(
        [
            InlineKeyboardButton(
                text="« Back to category", callback_data=f"cat:{product['category_id']}"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quantities(product_id: int, max_quantity: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=str(number), callback_data=f"qty:{product_id}:{number}")
        for number in range(1, max_quantity + 1)
    ]
    rows = [buttons[index : index + 5] for index in range(0, len(buttons), 5)]
    rows.append([InlineKeyboardButton(text="Cancel", callback_data="order:abort")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_methods(methods: tuple[PaymentMethod, ...]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=method.label, callback_data=f"pay:{method.key}")]
        for method in methods
    ]
    rows.append([InlineKeyboardButton(text="Cancel", callback_data="order:abort")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Place order", callback_data="order:confirm")],
            [InlineKeyboardButton(text="Cancel", callback_data="order:abort")],
        ]
    )


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📦 Products", callback_data="adm:products"),
                InlineKeyboardButton(text="🧾 Orders", callback_data="adm:orders"),
            ],
            [
                InlineKeyboardButton(text="📊 Stats", callback_data="adm:stats"),
                InlineKeyboardButton(text="📁 Export CSV", callback_data="adm:export"),
            ],
        ]
    )
