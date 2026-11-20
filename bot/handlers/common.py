"""Shared handler helpers: admin filter and buyer/admin notifications."""

from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter
from aiogram.types import Message

from ..config import Settings
from ..formatting import payment_label


class IsAdmin(BaseFilter):
    def __init__(self, admin_ids: frozenset[int]) -> None:
        self.admin_ids = set(admin_ids)

    async def __call__(self, event: Message) -> bool:
        return event.from_user is not None and event.from_user.id in self.admin_ids


async def notify_admins(bot: Bot, settings: Settings, text: str) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except TelegramAPIError:
            continue


async def notify_buyer(bot: Bot, order: dict, text: str) -> bool:
    try:
        await bot.send_message(order["user_id"], text)
        return True
    except TelegramAPIError:
        return False


def order_for_admin(order: dict, settings: Settings, money) -> str:
    """Compact admin view with customer data and status history."""
    lines = [
        f"<b>Order {escape(order['order_number'])}</b>",
        f"Status: {escape(order['status'])}",
        f"Total: {money(order['total_cents'], settings.currency)}",
        f"Customer: {escape(order['customer_name'])} · {escape(order['phone'])}",
        f"Address: {escape(order['address'])}",
        f"Payment: {escape(payment_label(settings, order['payment_method']))}",
    ]
    if order.get("tracking_number"):
        lines.append(f"Tracking: <code>{escape(order['tracking_number'])}</code>")
    lines.append("")
    for item in order["items"]:
        lines.append(
            f"• {item['quantity']}x {escape(item['product_name'])} — "
            f"{money(item['subtotal_cents'], settings.currency)}"
        )
    lines.append("")
    lines.append("<b>History</b>")
    for event in order["events"]:
        comment = f" — {escape(event['comment'])}" if event["comment"] else ""
        lines.append(f"• {event['created_at'][:16].replace('T', ' ')} {event['status']}{comment}")
    return "\n".join(lines)
