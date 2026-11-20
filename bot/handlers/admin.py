"""Admin commands: products, stock, orders, tracking and CSV export."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import keyboards as kb
from .. import services
from ..config import STATUSES, Settings
from ..db import Database
from ..formatting import money, status_label
from .common import IsAdmin, notify_buyer, order_for_admin

router = Router(name="admin")


class ShopErrorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except services.ShopError as exc:
            target = event.message if isinstance(event, CallbackQuery) else event
            await target.answer(f"⚠️ {escape(str(exc))}")
            return None


router.message.middleware(ShopErrorMiddleware())
router.callback_query.middleware(ShopErrorMiddleware())


def build_admin_router(admin_ids: frozenset[int]) -> Router:
    admin_filter = IsAdmin(admin_ids)
    router.message.filter(admin_filter)
    router.callback_query.filter(admin_filter)
    return router


def _int(value: str, name: str) -> int:
    try:
        return int(value.strip())
    except ValueError as exc:
        raise services.ValidationError(f"{name} must be a whole number.") from exc


def _split_args(args: str | None, usage: str, separators: str = " ") -> list[str]:
    if not args or not args.strip():
        raise services.ValidationError(f"Usage: {usage}")
    return [part.strip() for part in args.split(separators) if part.strip()]


@router.message(Command("admin"))
async def admin_home(message: Message, settings: Settings, db: Database) -> None:
    stats = await services.shop_stats(db, settings.low_stock_threshold)
    methods = "\n".join(f"• {escape(method.label)}" for method in settings.payment_methods)
    await message.answer(
        "<b>Admin panel</b>\n\n"
        "<b>Products</b>\n"
        "/addcategory &lt;name&gt;\n"
        "/addproduct Name | 12.50 | 10 | Category | Description\n"
        "/editproduct &lt;id&gt; price|stock|name|description|category|active &lt;value&gt;\n"
        "/setphoto &lt;id&gt; &lt;file_id or URL&gt;\n"
        "/setstock &lt;id&gt; &lt;qty&gt; · /restock &lt;id&gt; &lt;+/-qty&gt;\n"
        "/toggleproduct &lt;id&gt;\n"
        "/products — list products\n\n"
        "<b>Orders</b>\n"
        "/orders [status] — recent orders\n"
        "/order &lt;number&gt; — details and history\n"
        "/setstatus &lt;number&gt; &lt;status&gt; [comment]\n"
        "/tracking &lt;number&gt; &lt;tracking number&gt;\n"
        "/export [status] — CSV file\n"
        "/stats — totals and low stock\n\n"
        f"<b>Statuses:</b> {', '.join(STATUSES)}\n"
        f"<b>Active products:</b> {stats['active_products']}\n"
        f"<b>Payment methods</b>\n{methods}",
        reply_markup=kb.admin_menu(),
    )


@router.callback_query(F.data == "adm:products")
async def admin_products_callback(
    callback: CallbackQuery, db: Database, settings: Settings
) -> None:
    await callback.answer()
    await callback.message.answer(await _products_text(db, settings))


@router.callback_query(F.data == "adm:orders")
async def admin_orders_callback(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    await callback.answer()
    await callback.message.answer(await _orders_text(db, None, settings))


@router.callback_query(F.data == "adm:stats")
async def admin_stats_callback(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    await callback.answer()
    await callback.message.answer(await _stats_text(db, settings))


@router.callback_query(F.data == "adm:export")
async def admin_export_callback(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    await callback.answer()
    await _send_csv(callback.message, db, None, bot)


@router.message(Command("addcategory"))
async def add_category(message: Message, command, db: Database) -> None:
    name = (command.args or "").strip()
    category_id = await services.ensure_category(db, name)
    await message.answer(f"✅ Category ready: <b>{escape(name)}</b> (id {category_id})")


@router.message(Command("addproduct"))
async def add_product(message: Message, command, db: Database, settings: Settings) -> None:
    parts = _split_args(
        command.args,
        "/addproduct Name | 12.50 | 10 | Category | Optional description",
        "|",
    )
    if len(parts) < 4:
        raise services.ValidationError(
            "Usage: /addproduct Name | 12.50 | 10 | Category | Optional description"
        )
    name, price, stock, category = parts[:4]
    description = " | ".join(parts[4:])
    category_id = await services.ensure_category(db, category)
    product = await services.add_product(
        db,
        category_id=category_id,
        name=name,
        price_cents=services.parse_price(price),
        stock=_int(stock, "stock"),
        description=description,
    )
    await message.answer(
        f"✅ Product #{product['id']} added: <b>{escape(product['name'])}</b> — "
        f"{money(product['price_cents'], settings.currency)} · stock {product['stock']}\n"
        f"Add a photo with /setphoto {product['id']} &lt;file_id or URL&gt;"
    )


@router.message(Command("editproduct"))
async def edit_product(message: Message, command, db: Database, settings: Settings) -> None:
    parts = _split_args(
        command.args, "/editproduct <id> price|stock|name|description|category|active <value>"
    )
    if len(parts) < 3:
        raise services.ValidationError(
            "Usage: /editproduct <id> price|stock|name|description|category|active <value>"
        )
    product_id = _int(parts[0], "id")
    field = parts[1].lower()
    value = " ".join(parts[2:])
    updates: dict = {}
    if field == "price":
        updates["price_cents"] = services.parse_price(value)
    elif field == "stock":
        updates["stock"] = _int(value, "stock")
    elif field in ("name", "description", "photo"):
        updates[field] = value
    elif field == "category":
        updates["category_id"] = await services.ensure_category(db, value)
    elif field == "active":
        updates["is_active"] = value.lower() in ("1", "true", "yes", "on")
    else:
        raise services.ValidationError(
            "Field must be price, stock, name, description, photo, category or active."
        )
    product = await services.update_product(db, product_id, **updates)
    await message.answer(
        f"✅ Product #{product['id']} updated: <b>{escape(product['name'])}</b> — "
        f"{money(product['price_cents'], settings.currency)} · stock {product['stock']} · "
        f"{'active' if product['is_active'] else 'hidden'}"
    )


@router.message(F.photo)
async def photo_file_id(message: Message) -> None:
    """Admins can forward a product photo to get its Telegram file_id."""
    file_id = message.photo[-1].file_id
    await message.answer(
        "Photo file_id:\n"
        f"<code>{escape(file_id)}</code>\n\n"
        "Attach it to a product with /setphoto &lt;product id&gt; &lt;file_id&gt;"
    )


@router.message(Command("setphoto"))
async def set_photo(message: Message, command, db: Database) -> None:
    parts = _split_args(command.args, "/setphoto <id> <file_id or URL>")
    if len(parts) < 2:
        raise services.ValidationError("Usage: /setphoto <id> <file_id or URL>")
    product = await services.update_product(db, _int(parts[0], "id"), photo=" ".join(parts[1:]))
    await message.answer(f"✅ Photo updated for <b>{escape(product['name'])}</b>.")


@router.message(Command("setstock"))
async def set_stock(message: Message, command, db: Database) -> None:
    parts = _split_args(command.args, "/setstock <id> <qty>")
    if len(parts) != 2:
        raise services.ValidationError("Usage: /setstock <id> <qty>")
    product = await services.set_stock(db, _int(parts[0], "id"), _int(parts[1], "stock"))
    await message.answer(
        f"✅ Stock for <b>{escape(product['name'])}</b> set to {product['stock']}."
    )


@router.message(Command("restock"))
async def restock(message: Message, command, db: Database) -> None:
    parts = _split_args(command.args, "/restock <id> <+/-qty>")
    if len(parts) != 2:
        raise services.ValidationError("Usage: /restock <id> <+/-qty>")
    product = await services.adjust_stock(db, _int(parts[0], "id"), _int(parts[1], "delta"))
    await message.answer(
        f"✅ Stock for <b>{escape(product['name'])}</b> is now {product['stock']}."
    )


@router.message(Command("toggleproduct"))
async def toggle_product(message: Message, command, db: Database) -> None:
    product_id = _int((command.args or "").strip(), "id")
    product = await services.get_product(db, product_id)
    if product is None:
        raise services.NotFound("Product not found.")
    updated = await services.update_product(db, product_id, is_active=not product["is_active"])
    state = "visible" if updated["is_active"] else "hidden"
    await message.answer(f"✅ <b>{escape(updated['name'])}</b> is now {state} in the catalog.")


@router.message(Command("products"))
async def list_products(message: Message, command, db: Database, settings: Settings) -> None:
    category_id = _int(command.args, "category id") if (command.args or "").strip() else None
    await message.answer(await _products_text(db, settings, category_id))


async def _products_text(db: Database, settings: Settings, category_id: int | None = None) -> str:
    products = await services.list_products(db, category_id, include_inactive=True)
    if not products:
        return "No products yet. Add one with /addproduct."
    lines = ["<b>Products</b>", ""]
    for product in products[:50]:
        hidden = "" if product["is_active"] else " · hidden"
        lines.append(
            f"#{product['id']} <b>{escape(product['name'])}</b> — "
            f"{money(product['price_cents'], settings.currency)} · stock {product['stock']} · "
            f"{escape(product['category_name'])}{hidden}"
        )
    return "\n".join(lines)


@router.message(Command("orders"))
async def list_orders(message: Message, command, db: Database, settings: Settings) -> None:
    status = (command.args or "").strip().lower() or None
    if status and status not in STATUSES:
        raise services.ValidationError(f"Status must be one of: {', '.join(STATUSES)}")
    await message.answer(await _orders_text(db, status, settings))


async def _orders_text(db: Database, status: str | None, settings: Settings) -> str:
    orders = await services.list_orders(db, status=status, limit=20)
    if not orders:
        return "No orders found."
    lines = [f"<b>Orders{f' — {status}' if status else ''}</b>", ""]
    for order in orders:
        lines.append(
            f"<code>{order['order_number']}</code> · "
            f"{money(order['total_cents'], settings.currency)} · "
            f"{status_label(order['status'])} · {escape(order['customer_name'])}"
        )
    lines.append("\nUse /order &lt;number&gt; for details.")
    return "\n".join(lines)


@router.message(Command("order"))
async def order_details(message: Message, command, db: Database, settings: Settings) -> None:
    number = (command.args or "").strip()
    if not number:
        raise services.ValidationError("Usage: /order <number>")
    order = await services.get_order(db, number)
    if order is None:
        raise services.NotFound("Order not found.")
    await message.answer(order_for_admin(order, settings, money))


@router.message(Command("setstatus"))
async def set_status(message: Message, command, db: Database, settings: Settings, bot: Bot) -> None:
    parts = _split_args(command.args, "/setstatus <number> <status> [comment]")
    if len(parts) < 2:
        raise services.ValidationError("Usage: /setstatus <number> <status> [comment]")
    number, status = parts[0], parts[1].lower()
    comment = " ".join(parts[2:]) or None
    order = await services.set_order_status(db, number, status, comment)
    notified = await notify_buyer(
        bot,
        order,
        f"<b>Order {escape(order['order_number'])} update</b>\n"
        f"Status: {escape(status_label(order['status']))}"
        + (f"\n{escape(comment)}" if comment else ""),
    )
    suffix = "Buyer notified." if notified else "Buyer could not be notified (bot blocked?)."
    await message.answer(
        f"✅ <code>{order['order_number']}</code> is now <b>{order['status']}</b>. {suffix}"
    )


@router.message(Command("tracking"))
async def set_tracking(
    message: Message, command, db: Database, settings: Settings, bot: Bot
) -> None:
    parts = _split_args(command.args, "/tracking <number> <tracking number>")
    if len(parts) < 2:
        raise services.ValidationError("Usage: /tracking <number> <tracking number>")
    number, tracking = parts[0], " ".join(parts[1:])
    order = await services.set_tracking(db, number, tracking)
    notified = await notify_buyer(
        bot,
        order,
        f"<b>Order {escape(order['order_number'])} shipped</b>\n"
        f"Tracking number: <code>{escape(order['tracking_number'])}</code>\n"
        f"Status: {escape(status_label(order['status']))}",
    )
    suffix = "Buyer notified." if notified else "Buyer could not be notified (bot blocked?)."
    await message.answer(f"✅ Tracking set for <code>{order['order_number']}</code>. {suffix}")


@router.message(Command("export"))
async def export(message: Message, command, db: Database, bot: Bot) -> None:
    status = (command.args or "").strip().lower() or None
    if status and status not in STATUSES:
        raise services.ValidationError(f"Status must be one of: {', '.join(STATUSES)}")
    await _send_csv(message, db, status, bot)


async def _send_csv(message: Message, db: Database, status: str | None, bot: Bot) -> None:
    csv_text = await services.export_orders_csv(db, status=status)
    filename = f"orders-{datetime.now(UTC):%Y%m%d-%H%M}.csv"
    await bot.send_document(
        chat_id=message.chat.id,
        document=BufferedInputFile(("\ufeff" + csv_text).encode("utf-8"), filename=filename),
        caption=f"Orders export{f' ({status})' if status else ''}",
    )


@router.message(Command("stats"))
async def stats(message: Message, db: Database, settings: Settings) -> None:
    await message.answer(await _stats_text(db, settings))


async def _stats_text(db: Database, settings: Settings) -> str:
    stats = await services.shop_stats(db, settings.low_stock_threshold)
    by_status = (
        ", ".join(
            f"{status}: {count}" for status, count in sorted(stats["orders_by_status"].items())
        )
        or "no orders yet"
    )
    low_stock = (
        ", ".join(
            f"#{item['id']} {escape(item['name'])} ({item['stock']})" for item in stats["low_stock"]
        )
        or "none"
    )
    return (
        "<b>Shop stats</b>\n"
        f"Active products: {stats['active_products']}\n"
        f"Revenue (paid+): {money(stats['revenue_cents'], settings.currency)}\n"
        f"Orders: {by_status}\n"
        f"Low stock (≤{settings.low_stock_threshold}): {low_stock}"
    )
