"""Message and money formatting helpers (HTML parse mode)."""

from __future__ import annotations

from html import escape

from .config import PaymentMethod, Settings

STATUS_LABELS = {
    "new": "New — awaiting payment",
    "confirmed": "Confirmed",
    "paid": "Paid",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}

STATUS_ICONS = {
    "new": "🕒",
    "confirmed": "📝",
    "paid": "💳",
    "shipped": "📦",
    "delivered": "✅",
    "cancelled": "❌",
}


def money(cents: int, currency: str = "USD") -> str:
    amount = f"{cents / 100:,.2f}"
    return f"${amount}" if currency.upper() == "USD" else f"{amount} {currency.upper()}"


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.title())


def payment_label(settings: Settings, key: str) -> str:
    for method in settings.payment_methods:
        if method.key == key:
            return method.label
    return key


def find_payment_method(settings: Settings, key: str) -> PaymentMethod | None:
    return next((method for method in settings.payment_methods if method.key == key), None)


def order_summary(order: dict, settings: Settings) -> str:
    lines = [
        f"<b>Order {escape(order['order_number'])}</b>",
        f"Status: {STATUS_ICONS.get(order['status'], '')} {escape(status_label(order['status']))}",
        "",
        "<b>Items</b>",
    ]
    for item in order.get("items", []):
        lines.append(
            f"• {item['quantity']}x {escape(item['product_name'])} — "
            f"{money(item['subtotal_cents'], settings.currency)}"
        )
    lines += [
        "",
        f"<b>Total:</b> {money(order['total_cents'], settings.currency)}",
        f"<b>Payment:</b> {escape(payment_label(settings, order['payment_method']))}",
        f"<b>Name:</b> {escape(order['customer_name'])}",
        f"<b>Phone:</b> {escape(order['phone'])}",
        f"<b>Address:</b> {escape(order['address'])}",
    ]
    if order.get("tracking_number"):
        lines.append(f"<b>Tracking:</b> <code>{escape(order['tracking_number'])}</code>")
    return "\n".join(lines)


def order_row(order: dict, currency: str) -> str:
    icon = STATUS_ICONS.get(order["status"], "")
    return (
        f"{icon} <code>{escape(order['order_number'])}</code> · "
        f"{money(order['total_cents'], currency)} · {escape(status_label(order['status']))}"
    )
