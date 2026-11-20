"""Business logic for catalog, orders, stock, tracking and CSV export.

Handlers stay thin; everything that touches money or stock lives here so it can
be tested without Telegram.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from .db import Database

MAX_QUANTITY = 99

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "new": {"confirmed", "paid", "cancelled"},
    "confirmed": {"paid", "cancelled"},
    "paid": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


class ShopError(Exception):
    """Base class for expected business errors."""


class NotFound(ShopError):
    pass


class ValidationError(ShopError):
    pass


class OutOfStock(ShopError):
    def __init__(self, product_name: str, requested: int, available: int) -> None:
        self.product_name = product_name
        self.requested = requested
        self.available = available
        super().__init__(f"Only {available} left of {product_name} (requested {requested})")


class InvalidTransition(ShopError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_price(value: str) -> int:
    """Convert a human price such as ``12.50`` into integer cents."""
    cleaned = value.strip().replace("$", "").replace(",", "")
    if not cleaned:
        raise ValidationError("price is required")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValidationError(f"invalid price: {value!r}") from exc
    if amount < 0:
        raise ValidationError("price cannot be negative")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError("price supports at most 2 decimal places")
    return int(amount * 100)


def validate_customer(name: str, phone: str, address: str) -> tuple[str, str, str]:
    name = " ".join(name.split())
    phone = phone.strip()
    address = " ".join(address.split())
    if not 2 <= len(name) <= 80:
        raise ValidationError("Please send your full name (2-80 characters).")
    if not 5 <= len(phone) <= 30 or not re.fullmatch(r"[0-9+()\-\s]+", phone):
        raise ValidationError("Please send a valid phone number.")
    if not 5 <= len(address) <= 300:
        raise ValidationError("Please send a delivery address (5-300 characters).")
    return name, phone, address


def _row(row) -> dict:
    return dict(row)


async def list_categories(db: Database) -> list[dict]:
    rows = await db.fetchall(
        """
        SELECT c.id, c.name, c.sort_order, COUNT(p.id) AS product_count
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id AND p.is_active = 1
        GROUP BY c.id
        ORDER BY c.sort_order, c.name
        """
    )
    return [_row(row) for row in rows]


async def ensure_category(db: Database, name: str) -> int:
    name = " ".join(name.split())
    if not 2 <= len(name) <= 60:
        raise ValidationError("Category name must be 2-60 characters.")
    existing = await db.fetchone("SELECT id FROM categories WHERE name = ?", (name,))
    if existing:
        return int(existing["id"])
    return await db.execute(
        "INSERT INTO categories(name, sort_order) VALUES(?, "
        "(SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories))",
        (name,),
    )


async def add_product(
    db: Database,
    *,
    category_id: int,
    name: str,
    price_cents: int,
    stock: int = 0,
    description: str = "",
    photo: str | None = None,
) -> dict:
    name = " ".join(name.split())
    if not 2 <= len(name) <= 100:
        raise ValidationError("Product name must be 2-100 characters.")
    if price_cents < 0:
        raise ValidationError("Price cannot be negative.")
    if stock < 0:
        raise ValidationError("Stock cannot be negative.")
    category = await db.fetchone("SELECT id FROM categories WHERE id = ?", (category_id,))
    if not category:
        raise NotFound("Category not found.")
    now = utc_now()
    product_id = await db.execute(
        """
        INSERT INTO products(category_id, name, description, price_cents, stock, photo,
                             is_active, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (category_id, name, description.strip(), price_cents, stock, photo, now, now),
    )
    product = await get_product(db, product_id)
    assert product is not None
    return product


async def get_product(db: Database, product_id: int) -> dict | None:
    row = await db.fetchone(
        """
        SELECT p.*, c.name AS category_name
        FROM products p JOIN categories c ON c.id = p.category_id
        WHERE p.id = ?
        """,
        (product_id,),
    )
    return _row(row) if row else None


async def list_products(
    db: Database,
    category_id: int | None = None,
    *,
    include_inactive: bool = False,
) -> list[dict]:
    clauses = []
    params: list[int] = []
    if category_id is not None:
        clauses.append("p.category_id = ?")
        params.append(category_id)
    if not include_inactive:
        clauses.append("p.is_active = 1")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = await db.fetchall(
        f"""
        SELECT p.*, c.name AS category_name
        FROM products p JOIN categories c ON c.id = p.category_id
        {where}
        ORDER BY p.name
        """,
        params,
    )
    return [_row(row) for row in rows]


async def update_product(db: Database, product_id: int, **fields) -> dict:
    allowed = {"name", "description", "price_cents", "stock", "photo", "category_id", "is_active"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValidationError(f"Unsupported product fields: {', '.join(sorted(unknown))}")
    if not fields:
        raise ValidationError("Nothing to update.")
    if "name" in fields:
        fields["name"] = " ".join(str(fields["name"]).split())
        if not 2 <= len(fields["name"]) <= 100:
            raise ValidationError("Product name must be 2-100 characters.")
    if "price_cents" in fields and fields["price_cents"] < 0:
        raise ValidationError("Price cannot be negative.")
    if "stock" in fields and fields["stock"] < 0:
        raise ValidationError("Stock cannot be negative.")
    if "category_id" in fields:
        category = await db.fetchone(
            "SELECT id FROM categories WHERE id = ?", (fields["category_id"],)
        )
        if not category:
            raise NotFound("Category not found.")
    if "is_active" in fields:
        fields["is_active"] = 1 if fields["is_active"] else 0
    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    await db.execute(
        f"UPDATE products SET {assignments} WHERE id = ?",
        (*fields.values(), product_id),
    )
    product = await get_product(db, product_id)
    if product is None:
        raise NotFound("Product not found.")
    return product


async def set_stock(db: Database, product_id: int, stock: int) -> dict:
    return await update_product(db, product_id, stock=stock)


async def adjust_stock(db: Database, product_id: int, delta: int) -> dict:
    product = await get_product(db, product_id)
    if product is None:
        raise NotFound("Product not found.")
    return await update_product(db, product_id, stock=product["stock"] + delta)


async def create_order(
    db: Database,
    *,
    user_id: int,
    username: str | None,
    customer_name: str,
    phone: str,
    address: str,
    payment_method: str,
    items: Sequence[tuple[int, int]],
    currency: str = "USD",
) -> dict:
    """Create an order and decrement stock atomically.

    Raises ``OutOfStock`` (and rolls back everything) when any line cannot be
    fulfilled. The stock update is guarded in SQL, so two concurrent buyers can
    never take the same last unit.
    """
    name, phone, address = validate_customer(customer_name, phone, address)
    if not payment_method:
        raise ValidationError("Choose a payment method.")
    if not items:
        raise ValidationError("Your cart is empty.")
    merged: dict[int, int] = {}
    for product_id, quantity in items:
        if not 1 <= quantity <= MAX_QUANTITY:
            raise ValidationError(f"Quantity must be between 1 and {MAX_QUANTITY}.")
        merged[product_id] = merged.get(product_id, 0) + quantity
    if any(quantity > MAX_QUANTITY for quantity in merged.values()):
        raise ValidationError(f"Quantity must be between 1 and {MAX_QUANTITY}.")

    now = utc_now()
    async with db.transaction() as conn:
        placeholders = ",".join("?" for _ in merged)
        cursor = await conn.execute(
            "SELECT id, name, price_cents, stock, is_active "
            f"FROM products WHERE id IN ({placeholders})",
            tuple(merged),
        )
        products = {row["id"]: row for row in await cursor.fetchall()}
        await cursor.close()

        for product_id, quantity in merged.items():
            product = products.get(product_id)
            if product is None or not product["is_active"]:
                raise NotFound("One of the products is no longer available.")
            if product["stock"] < quantity:
                raise OutOfStock(product["name"], quantity, product["stock"])

        lines = []
        total_cents = 0
        for product_id, quantity in merged.items():
            product = products[product_id]
            unit_price = product["price_cents"]
            subtotal = unit_price * quantity
            total_cents += subtotal
            lines.append((product_id, product["name"], unit_price, quantity, subtotal))

        cursor = await conn.execute(
            """
            INSERT INTO orders(order_number, user_id, username, customer_name, phone, address,
                               payment_method, status, total_cents, currency,
                               created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?)
            """,
            (
                f"PENDING-{uuid.uuid4().hex}",
                user_id,
                username,
                name,
                phone,
                address,
                payment_method,
                total_cents,
                currency,
                now,
                now,
            ),
        )
        order_id = cursor.lastrowid
        assert order_id is not None
        await cursor.close()
        order_number = f"SB-{order_id:06d}"
        await conn.execute(
            "UPDATE orders SET order_number = ? WHERE id = ?", (order_number, order_id)
        )

        for product_id, product_name, unit_price, quantity, subtotal in lines:
            cursor = await conn.execute(
                "UPDATE products SET stock = stock - ?, updated_at = ? "
                "WHERE id = ? AND stock >= ? AND is_active = 1",
                (quantity, now, product_id, quantity),
            )
            if cursor.rowcount != 1:
                await cursor.close()
                raise OutOfStock(product_name, quantity, 0)
            await cursor.close()
            await conn.execute(
                """
                INSERT INTO order_items(order_id, product_id, product_name, unit_price_cents,
                                        quantity, subtotal_cents)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (order_id, product_id, product_name, unit_price, quantity, subtotal),
            )

        await conn.execute(
            "INSERT INTO order_events(order_id, status, comment, created_at) "
            "VALUES(?, 'new', ?, ?)",
            (order_id, "Order created", now),
        )

    order = await get_order(db, order_number)
    assert order is not None
    return order


async def get_order(db: Database, order_number: str) -> dict | None:
    number = order_number.strip().upper()
    row = await db.fetchone("SELECT * FROM orders WHERE order_number = ?", (number,))
    if row is None:
        return None
    order = _row(row)
    items = await db.fetchall(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)
    )
    events = await db.fetchall(
        "SELECT status, comment, created_at FROM order_events WHERE order_id = ? ORDER BY id",
        (order["id"],),
    )
    order["items"] = [_row(item) for item in items]
    order["events"] = [_row(event) for event in events]
    return order


async def get_user_order(db: Database, order_number: str, user_id: int) -> dict | None:
    order = await get_order(db, order_number)
    if order is None or order["user_id"] != user_id:
        return None
    return order


async def list_user_orders(db: Database, user_id: int, limit: int = 10) -> list[dict]:
    rows = await db.fetchall(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
    )
    return [_row(row) for row in rows]


async def list_orders(db: Database, status: str | None = None, limit: int = 20) -> list[dict]:
    if status:
        rows = await db.fetchall(
            "SELECT * FROM orders WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit)
        )
    else:
        rows = await db.fetchall("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
    return [_row(row) for row in rows]


async def set_order_status(
    db: Database, order_number: str, new_status: str, comment: str | None = None
) -> dict:
    new_status = new_status.strip().lower()
    if new_status not in ALLOWED_TRANSITIONS:
        raise ValidationError(f"Unknown status: {new_status}")
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE order_number = ?", (order_number.strip().upper(),)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            raise NotFound("Order not found.")
        current = row["status"]
        if new_status not in ALLOWED_TRANSITIONS[current]:
            raise InvalidTransition(f"Cannot change {current} -> {new_status}.")
        now = utc_now()
        await conn.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, row["id"]),
        )
        if new_status == "cancelled":
            items = await (
                await conn.execute(
                    "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
                    (row["id"],),
                )
            ).fetchall()
            for item in items:
                if item["product_id"] is not None:
                    await conn.execute(
                        "UPDATE products SET stock = stock + ?, updated_at = ? WHERE id = ?",
                        (item["quantity"], now, item["product_id"]),
                    )
        await conn.execute(
            "INSERT INTO order_events(order_id, status, comment, created_at) VALUES(?, ?, ?, ?)",
            (row["id"], new_status, comment, now),
        )
    order = await get_order(db, order_number)
    assert order is not None
    return order


async def set_tracking(db: Database, order_number: str, tracking_number: str) -> dict:
    tracking_number = " ".join(tracking_number.split())
    if not 3 <= len(tracking_number) <= 64:
        raise ValidationError("Tracking number must be 3-64 characters.")
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE order_number = ?", (order_number.strip().upper(),)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            raise NotFound("Order not found.")
        if row["status"] not in ("paid", "shipped"):
            raise InvalidTransition("Tracking can only be set for paid or shipped orders.")
        now = utc_now()
        await conn.execute(
            "UPDATE orders SET tracking_number = ?, status = 'shipped', updated_at = ? "
            "WHERE id = ?",
            (tracking_number, now, row["id"]),
        )
        if row["status"] == "paid":
            await conn.execute(
                "INSERT INTO order_events(order_id, status, comment, created_at) "
                "VALUES(?, 'shipped', ?, ?)",
                (row["id"], f"Tracking: {tracking_number}", now),
            )
    order = await get_order(db, order_number)
    assert order is not None
    return order


def _csv_cell(value: str) -> str:
    """Neutralize spreadsheet formula injection without mangling phone numbers."""
    if value and value[0] in ("=", "@", "\t", "\r"):
        return "'" + value
    if value and value[0] in ("+", "-") and any(character.isalpha() for character in value):
        return "'" + value
    return value


async def export_orders_csv(db: Database, status: str | None = None) -> str:
    orders = await list_orders(db, status=status, limit=100_000)
    orders.reverse()
    items_by_order: dict[int, list] = {}
    if orders:
        placeholders = ",".join("?" for _ in orders)
        rows = await db.fetchall(
            "SELECT order_id, product_name, quantity FROM order_items "
            f"WHERE order_id IN ({placeholders}) ORDER BY id",
            [order["id"] for order in orders],
        )
        for row in rows:
            items_by_order.setdefault(row["order_id"], []).append(row)

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
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
    )
    for order in orders:
        items = items_by_order.get(order["id"], [])
        summary = "; ".join(f"{item['quantity']}x {item['product_name']}" for item in items)
        writer.writerow(
            [
                _csv_cell(order["order_number"]),
                _csv_cell(order["created_at"]),
                _csv_cell(order["status"]),
                _csv_cell(order["customer_name"]),
                _csv_cell(order["phone"]),
                _csv_cell(order["address"]),
                _csv_cell(order["payment_method"]),
                f"{order['total_cents'] / 100:.2f}",
                _csv_cell(order["currency"]),
                _csv_cell(order["tracking_number"] or ""),
                _csv_cell(summary),
            ]
        )
    return buffer.getvalue()


async def shop_stats(db: Database, low_stock_threshold: int = 5) -> dict:
    status_rows = await db.fetchall("SELECT status, COUNT(*) AS count FROM orders GROUP BY status")
    revenue = await db.fetchone(
        "SELECT COALESCE(SUM(total_cents), 0) AS cents FROM orders "
        "WHERE status IN ('paid', 'shipped', 'delivered')"
    )
    low_stock = await db.fetchall(
        "SELECT id, name, stock FROM products WHERE is_active = 1 AND stock <= ? ORDER BY stock",
        (low_stock_threshold,),
    )
    products = await db.fetchone("SELECT COUNT(*) AS count FROM products WHERE is_active = 1")
    return {
        "orders_by_status": {row["status"]: row["count"] for row in status_rows},
        "revenue_cents": int(revenue["cents"]) if revenue else 0,
        "active_products": int(products["count"]) if products else 0,
        "low_stock": [_row(row) for row in low_stock],
    }
