"""Customer-facing handlers: catalog, cart and order placement."""

from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import services
from ..config import Settings
from ..db import Database
from ..formatting import (
    find_payment_method,
    money,
    order_row,
    order_summary,
    payment_label,
    status_label,
)
from ..states import OrderFlow, TrackFlow
from .common import notify_admins

router = Router(name="catalog")


@router.message(CommandStart())
@router.message(Command("shop"))
async def start(message: Message, settings: Settings) -> None:
    await message.answer(
        f"<b>{escape(settings.shop_name)}</b>\n\n"
        "Browse the catalog, place an order and pay using the instructions shown "
        "after checkout. You can track your order at any time.",
        reply_markup=kb.start_menu(),
    )


@router.callback_query(F.data == "menu:home")
async def menu_home(callback: CallbackQuery, settings: Settings) -> None:
    await callback.answer()
    await callback.message.edit_text(
        f"<b>{escape(settings.shop_name)}</b>\n\nWhat would you like to do?",
        reply_markup=kb.start_menu(),
    )


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery, settings: Settings) -> None:
    await callback.answer()
    await callback.message.edit_text(help_text(settings), reply_markup=kb.start_menu())


@router.message(Command("help"))
async def help_command(message: Message, settings: Settings) -> None:
    await message.answer(help_text(settings), reply_markup=kb.start_menu())


def help_text(settings: Settings) -> str:
    methods = "\n".join(f"• {escape(method.label)}" for method in settings.payment_methods)
    return (
        "<b>How it works</b>\n"
        "1. Pick a product and quantity.\n"
        "2. Send your name, phone and delivery address.\n"
        "3. Choose a payment method and confirm.\n"
        "4. Follow the payment instructions shown after checkout.\n\n"
        "<b>Commands</b>\n"
        "/shop — catalog\n"
        "/track &lt;order number&gt; — order status and tracking\n"
        "/orders — your recent orders\n"
        "/cancel — cancel the current checkout\n\n"
        f"<b>Payment methods</b>\n{methods}"
    )


@router.callback_query(F.data == "menu:catalog")
async def show_categories(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    categories = await services.list_categories(db)
    if not categories:
        await callback.message.edit_text("The catalog is empty. Please check back soon.")
        return
    await callback.message.edit_text(
        "<b>Categories</b>\nChoose a category:", reply_markup=kb.categories(categories)
    )


@router.callback_query(F.data.startswith("cat:"))
async def show_products(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    await callback.answer()
    category_id = int(callback.data.split(":", 1)[1])
    categories = await services.list_categories(db)
    category = next((item for item in categories if item["id"] == category_id), None)
    if category is None:
        await callback.message.edit_text("Category not found.", reply_markup=kb.start_menu())
        return
    products = await services.list_products(db, category_id)
    if not products:
        await callback.message.edit_text(
            f"<b>{escape(category['name'])}</b>\n\nNo products in this category yet.",
            reply_markup=kb.categories(categories),
        )
        return
    await callback.message.edit_text(
        f"<b>{escape(category['name'])}</b>\nChoose a product:",
        reply_markup=kb.products(products),
    )


@router.callback_query(F.data.startswith("prod:"))
async def show_product(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    await callback.answer()
    product = await services.get_product(db, int(callback.data.split(":", 1)[1]))
    if product is None or not product["is_active"]:
        await callback.message.answer("This product is no longer available.")
        return
    await send_product_card(callback.message, product, settings)


async def send_product_card(message: Message, product: dict, settings: Settings) -> None:
    stock_line = f"In stock: {product['stock']}" if product["stock"] > 0 else "Out of stock"
    caption = (
        f"<b>{escape(product['name'])}</b>\n"
        f"{escape(product['description']) or '—'}\n\n"
        f"Price: <b>{money(product['price_cents'], settings.currency)}</b>\n"
        f"{stock_line}"
    )
    markup = kb.product(product)
    if product["photo"]:
        try:
            await message.answer_photo(product["photo"], caption=caption, reply_markup=markup)
            return
        except TelegramAPIError:
            pass
    await message.answer(caption, reply_markup=markup)


@router.callback_query(F.data.startswith("buy:"))
async def buy(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    await callback.answer()
    product = await services.get_product(db, int(callback.data.split(":", 1)[1]))
    if product is None or not product["is_active"] or product["stock"] <= 0:
        await callback.message.answer("Sorry, this product is out of stock.")
        return
    await state.set_state(OrderFlow.quantity)
    await state.update_data(product_id=product["id"])
    max_quantity = min(product["stock"], 5)
    await callback.message.answer(
        f"<b>{escape(product['name'])}</b>\n"
        f"Price: {money(product['price_cents'], settings.currency)}\n\n"
        "How many would you like? Tap a number or type a quantity.",
        reply_markup=kb.quantities(product["id"], max_quantity),
    )


async def _accept_quantity(
    message: Message, state: FSMContext, db: Database, product_id: int, quantity: int
) -> None:
    product = await services.get_product(db, product_id)
    if product is None or not product["is_active"]:
        await state.clear()
        await message.answer("This product is no longer available.")
        return
    if not 1 <= quantity <= services.MAX_QUANTITY:
        await message.answer(f"Please choose a quantity between 1 and {services.MAX_QUANTITY}.")
        return
    if quantity > product["stock"]:
        await message.answer(f"Only {product['stock']} left. Please choose a smaller quantity.")
        return
    await state.update_data(quantity=quantity)
    await state.set_state(OrderFlow.name)
    await message.answer(
        f"Added {quantity}x {escape(product['name'])}.\n\n<b>Step 2 of 5</b> — send your full name."
    )


@router.callback_query(F.data.startswith("qty:"))
async def quantity_callback(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await callback.answer()
    _, product_id, quantity = callback.data.split(":")
    if await state.get_state() != OrderFlow.quantity.state:
        await callback.message.answer("Checkout expired. Please open /shop and start again.")
        return
    data = await state.get_data()
    if data.get("product_id") != int(product_id):
        await callback.message.answer("Checkout expired. Please open /shop and start again.")
        return
    await _accept_quantity(callback.message, state, db, int(product_id), int(quantity))


@router.message(OrderFlow.quantity, ~F.text.startswith("/"))
async def quantity_text(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    product_id = data.get("product_id")
    if product_id is None:
        await state.clear()
        await message.answer("Checkout expired. Please open /shop and start again.")
        return
    try:
        quantity = int((message.text or "").strip())
    except ValueError:
        await message.answer("Please send a number, for example: 2")
        return
    await _accept_quantity(message, state, db, int(product_id), quantity)


@router.message(OrderFlow.name, ~F.text.startswith("/"))
async def collect_name(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split())
    if not 2 <= len(name) <= 80:
        await message.answer("Please send your full name (2-80 characters).")
        return
    await state.update_data(customer_name=name)
    await state.set_state(OrderFlow.phone)
    await message.answer("<b>Step 3 of 5</b> — send your phone number.")


@router.message(OrderFlow.phone, ~F.text.startswith("/"))
async def collect_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    try:
        services.validate_customer("Valid Name", phone, "Valid address")
    except services.ValidationError:
        await message.answer("Please send a valid phone number, for example: +373 60 000 000")
        return
    await state.update_data(phone=phone)
    await state.set_state(OrderFlow.address)
    await message.answer(
        "<b>Step 4 of 5</b> — send the delivery address (street, city, postal code)."
    )


@router.message(OrderFlow.address, ~F.text.startswith("/"))
async def collect_address(message: Message, state: FSMContext, settings: Settings) -> None:
    address = " ".join((message.text or "").split())
    if not 5 <= len(address) <= 300:
        await message.answer("Please send a delivery address (5-300 characters).")
        return
    await state.update_data(address=address)
    await state.set_state(OrderFlow.payment)
    await message.answer(
        "<b>Step 5 of 5</b> — choose a payment method.",
        reply_markup=kb.payment_methods(settings.payment_methods),
    )


@router.callback_query(F.data.startswith("pay:"))
async def choose_payment(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings
) -> None:
    await callback.answer()
    if await state.get_state() != OrderFlow.payment.state:
        await callback.message.answer("Checkout expired. Please open /shop and start again.")
        return
    key = callback.data.split(":", 1)[1]
    method = find_payment_method(settings, key)
    if method is None:
        await callback.message.answer("Unknown payment method. Please choose again.")
        return
    data = await state.get_data()
    product = await services.get_product(db, int(data["product_id"]))
    if product is None:
        await state.clear()
        await callback.message.answer("This product is no longer available.")
        return
    await state.update_data(payment_method=key)
    await state.set_state(OrderFlow.confirm)
    quantity = int(data["quantity"])
    total = product["price_cents"] * quantity
    summary = (
        "<b>Review your order</b>\n\n"
        f"{quantity}x {escape(product['name'])} — {money(total, settings.currency)}\n"
        f"Total: <b>{money(total, settings.currency)}</b>\n\n"
        f"Name: {escape(data['customer_name'])}\n"
        f"Phone: {escape(data['phone'])}\n"
        f"Address: {escape(data['address'])}\n"
        f"Payment: {escape(method.label)}"
    )
    await callback.message.answer(summary, reply_markup=kb.confirm())


@router.callback_query(F.data == "order:abort")
async def abort_order(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("Order cancelled.", reply_markup=kb.start_menu())


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Checkout cancelled.", reply_markup=kb.start_menu())


@router.callback_query(F.data == "order:confirm")
async def confirm_order(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    await callback.answer()
    data = await state.get_data()
    required = {"product_id", "quantity", "customer_name", "phone", "address", "payment_method"}
    if await state.get_state() != OrderFlow.confirm.state or not required.issubset(data):
        await callback.message.answer("Checkout expired. Please open /shop and start again.")
        return
    try:
        order = await services.create_order(
            db,
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            customer_name=data["customer_name"],
            phone=data["phone"],
            address=data["address"],
            payment_method=data["payment_method"],
            items=[(int(data["product_id"]), int(data["quantity"]))],
            currency=settings.currency,
        )
    except services.OutOfStock as exc:
        await state.clear()
        await callback.message.answer(
            f"Sorry — {escape(str(exc))}. Please order a smaller quantity."
        )
        return
    except services.ShopError as exc:
        await callback.message.answer(f"Could not place the order: {escape(str(exc))}")
        return

    await state.clear()
    method = find_payment_method(settings, order["payment_method"])
    instructions = method.instructions if method else "Contact us for payment details."
    label = payment_label(settings, order["payment_method"])
    await callback.message.answer(
        f"<b>Order {escape(order['order_number'])} placed</b>\n"
        f"Total: <b>{money(order['total_cents'], settings.currency)}</b>\n\n"
        f"<b>Payment — {escape(label)}</b>\n{escape(instructions)}\n\n"
        f"Keep your order number: <code>{escape(order['order_number'])}</code>\n"
        f"Track it any time with /track {escape(order['order_number'])}",
        reply_markup=kb.start_menu(),
    )
    await notify_admins(
        bot,
        settings,
        f"🆕 New order <code>{escape(order['order_number'])}</code>\n"
        f"{money(order['total_cents'], settings.currency)} · {escape(order['customer_name'])}\n"
        f"/order {escape(order['order_number'])}",
    )


@router.callback_query(F.data == "menu:orders")
async def my_orders(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    await callback.answer()
    orders = await services.list_user_orders(db, callback.from_user.id)
    if not orders:
        await callback.message.answer("You have no orders yet. Open /shop to browse the catalog.")
        return
    lines = ["<b>Your recent orders</b>", ""]
    lines += [order_row(order, settings.currency) for order in orders[:10]]
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data == "menu:track")
async def track_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(TrackFlow.number)
    await callback.message.answer("Send your order number, for example: <code>SB-000001</code>")


@router.message(Command("track"))
async def track_command(
    message: Message, command, state: FSMContext, db: Database, settings: Settings
) -> None:
    number = (command.args or "").strip()
    if not number:
        await state.set_state(TrackFlow.number)
        await message.answer("Send your order number, for example: <code>SB-000001</code>")
        return
    await send_order_status(message, db, settings, number, message.from_user.id)


@router.message(Command("orders"))
async def orders_command(message: Message, db: Database, settings: Settings) -> None:
    orders = await services.list_user_orders(db, message.from_user.id)
    if not orders:
        await message.answer("You have no orders yet. Open /shop to browse the catalog.")
        return
    lines = ["<b>Your recent orders</b>", ""]
    lines += [order_row(order, settings.currency) for order in orders[:10]]
    await message.answer("\n".join(lines))


@router.message(TrackFlow.number, ~F.text.startswith("/"))
async def track_number(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    number = (message.text or "").strip()
    if not number:
        await message.answer("Please send an order number, for example: <code>SB-000001</code>")
        return
    found = await send_order_status(message, db, settings, number, message.from_user.id)
    if found:
        await state.clear()


async def send_order_status(
    message: Message, db: Database, settings: Settings, number: str, user_id: int
) -> bool:
    order = await services.get_user_order(db, number, user_id)
    if order is None:
        await message.answer(
            "No order with that number was found in your account. "
            "Check the number and try again, or contact support."
        )
        return False
    text = order_summary(order, settings)
    if order["events"]:
        history = "\n".join(
            f"• {event['created_at'][:16].replace('T', ' ')} — {status_label(event['status'])}"
            for event in order["events"][-5:]
        )
        text += f"\n\n<b>History</b>\n{history}"
    await message.answer(text)
    return True
