"""
database.py — робота з базою даних SQLite
Таблиці: products, users, interactions, sessions, favorites,
         user_profiles, orders, order_items
"""
import sqlite3
import json
import logging
import datetime
from contextlib import contextmanager
from config import DB_PATH

logger = logging.getLogger(__name__)

_PRODUCT_COLUMNS = {
    "name", "category", "brand", "price", "sizes", "colors",
    "material", "description", "in_stock", "image_url",
}


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                category    TEXT    NOT NULL,
                brand       TEXT    NOT NULL,
                price       REAL    NOT NULL,
                sizes       TEXT    NOT NULL,
                colors      TEXT    NOT NULL,
                material    TEXT    NOT NULL,
                description TEXT    DEFAULT '',
                image_url   TEXT    DEFAULT '',
                in_stock    INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                name        TEXT,
                preferences TEXT    DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS interactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                product_id  INTEGER NOT NULL,
                action      TEXT    NOT NULL,
                timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                user_id     INTEGER PRIMARY KEY,
                context     TEXT    DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS favorites (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                product_id  INTEGER NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, product_id)
            );

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id          INTEGER PRIMARY KEY,
                first_name       TEXT    NOT NULL DEFAULT '',
                last_name        TEXT    NOT NULL DEFAULT '',
                phone            TEXT    NOT NULL DEFAULT '',
                delivery_address TEXT    NOT NULL DEFAULT '',
                created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                order_code  TEXT    NOT NULL UNIQUE,
                total       REAL    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'pending',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id    INTEGER NOT NULL,
                product_id  INTEGER NOT NULL,
                quantity    INTEGER NOT NULL DEFAULT 1,
                price       REAL    NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            );

            CREATE TABLE IF NOT EXISTS query_intents (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                category    TEXT,
                min_price   REAL,
                max_price   REAL,
                size        TEXT,
                color       TEXT,
                timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            -- Індекси для прискорення запитів
            CREATE INDEX IF NOT EXISTS idx_interactions_user
                ON interactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_favorites_user
                ON favorites(user_id);
            CREATE INDEX IF NOT EXISTS idx_query_intents_user
                ON query_intents(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_user
                ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_order_items_order
                ON order_items(order_id);
            CREATE INDEX IF NOT EXISTS idx_products_category
                ON products(category);
        """)


# ── Міграція: додати image_url якщо його немає ───────────────────────────────

def migrate_db():
    """Додає нові колонки до існуючої БД (безпечно — ігнорує якщо вже є)."""
    with get_connection() as conn:
        try:
            conn.execute("ALTER TABLE products ADD COLUMN image_url TEXT DEFAULT ''")
            logger.info("Міграція: додано колонку image_url")
        except sqlite3.OperationalError:
            pass  # колонка вже існує


# ── PRODUCTS ──────────────────────────────────────────────────────────────────

def get_all_products(in_stock_only=True):
    with get_connection() as conn:
        if in_stock_only:
            rows = conn.execute(
                "SELECT * FROM products WHERE in_stock = 1"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM products").fetchall()
        return [dict(r) for r in rows]


def get_product_by_id(product_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        return dict(row) if row else None


def search_products(query="", category=None, min_price=None,
                    max_price=None, size=None, color=None):
    with get_connection() as conn:
        sql = "SELECT * FROM products WHERE in_stock = 1"
        params = []

        if query:
            sql += (" AND (name LIKE ? OR description LIKE ?"
                    " OR brand LIKE ? OR material LIKE ?)")
            q = f"%{query}%"
            params.extend([q, q, q, q])
        if category:
            sql += " AND LOWER(category) = LOWER(?)"
            params.append(category)
        if min_price is not None:
            sql += " AND price >= ?"
            params.append(min_price)
        if max_price is not None:
            sql += " AND price <= ?"
            params.append(max_price)
        if size:
            sql += " AND sizes LIKE ?"
            params.append(f'%"{size}"%')
        if color:
            sql += " AND colors LIKE ?"
            params.append(f'%"{color}"%')

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def get_categories():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM products WHERE in_stock = 1 "
            "ORDER BY category"
        ).fetchall()
        return [r[0] for r in rows]


def add_product(name, category, brand, price, sizes, colors,
                material, description="", image_url=""):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO products
               (name, category, brand, price, sizes, colors,
                material, description, image_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, category, brand, price,
             json.dumps(sizes, ensure_ascii=False),
             json.dumps(colors, ensure_ascii=False),
             material, description, image_url)
        )


def update_product(product_id: int, **kwargs):
    with get_connection() as conn:
        for key, value in kwargs.items():
            if key not in _PRODUCT_COLUMNS:
                logger.warning("update_product: невідома колонка %r", key)
                continue
            if key in ("sizes", "colors") and isinstance(value, list):
                value = json.dumps(value, ensure_ascii=False)
            conn.execute(
                f"UPDATE products SET {key} = ? WHERE id = ?",
                (value, product_id)
            )


def delete_product(product_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))


# ── USERS & SESSIONS ─────────────────────────────────────────────────────────

def get_or_create_user(user_id: int, name: str = ""):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (user_id, name, preferences) VALUES (?, ?, '{}')",
                (user_id, name)
            )


def get_session(user_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT context FROM sessions WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                return {}
        return {}


def update_session(user_id: int, context: dict):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (user_id, context) VALUES (?, ?)",
            (user_id, json.dumps(context, ensure_ascii=False))
        )


# ── INTERACTIONS ──────────────────────────────────────────────────────────────

def log_interaction(user_id: int, product_id: int, action: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO interactions (user_id, product_id, action) VALUES (?, ?, ?)",
            (user_id, product_id, action)
        )


def get_user_interactions(user_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT product_id, action FROM interactions WHERE user_id = ?",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── FAVORITES ─────────────────────────────────────────────────────────────────

def toggle_favorite(user_id: int, product_id: int) -> bool:
    """Додає або видаляє з вибраного. Повертає True якщо додано, False якщо видалено."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM favorites WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        ).fetchone()
        if row:
            conn.execute(
                "DELETE FROM favorites WHERE user_id = ? AND product_id = ?",
                (user_id, product_id)
            )
            return False
        else:
            conn.execute(
                "INSERT INTO favorites (user_id, product_id) VALUES (?, ?)",
                (user_id, product_id)
            )
            return True


def get_favorites(user_id: int) -> list:
    """Повертає список товарів з вибраного."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT p.* FROM favorites f
               JOIN products p ON f.product_id = p.id
               WHERE f.user_id = ?
               ORDER BY f.created_at DESC""",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def is_favorite(user_id: int, product_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM favorites WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        ).fetchone()
        return row is not None


# ── USER PROFILES ─────────────────────────────────────────────────────────────

def get_user_profile(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def save_user_profile(user_id: int, first_name: str, last_name: str,
                      phone: str, delivery_address: str):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO user_profiles
               (user_id, first_name, last_name, phone, delivery_address)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, first_name, last_name, phone, delivery_address)
        )


# ── ORDERS ────────────────────────────────────────────────────────────────────

def generate_order_code() -> str:
    """Генерує унікальний код замовлення: NZV-YYMMDD-XXX."""
    now = datetime.datetime.now()
    date_part = now.strftime("%y%m%d")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE order_code LIKE ?",
            (f"NZV-{date_part}-%",)
        ).fetchone()
        seq = (row[0] or 0) + 1
    return f"NZV-{date_part}-{seq:03d}"


def create_order(user_id: int, cart: dict) -> dict | None:
    """
    Створює замовлення з кошика.
    cart: {product_id_str: quantity, ...}
    Повертає dict з даними замовлення або None якщо кошик порожній.
    """
    if not cart:
        return None

    order_code = generate_order_code()
    total = 0.0
    items = []

    for pid_str, qty in cart.items():
        product = get_product_by_id(int(pid_str))
        if product and qty > 0:
            subtotal = product["price"] * qty
            total += subtotal
            items.append({
                "product_id": product["id"],
                "name": product["name"],
                "quantity": qty,
                "price": product["price"],
                "subtotal": subtotal,
            })

    if not items:
        return None

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO orders (user_id, order_code, total, status) VALUES (?, ?, ?, 'pending')",
            (user_id, order_code, total)
        )
        order_id = cursor.lastrowid

        for item in items:
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)",
                (order_id, item["product_id"], item["quantity"], item["price"])
            )

    return {
        "order_id": order_id,
        "order_code": order_code,
        "total": total,
        "items": items,
        "status": "pending",
    }


def get_user_orders(user_id: int) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_order_by_code(order_code: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE order_code = ?", (order_code,)
        ).fetchone()
        return dict(row) if row else None


def get_order_items(order_id: int) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT oi.*, p.name as product_name
               FROM order_items oi
               JOIN products p ON oi.product_id = p.id
               WHERE oi.order_id = ?""",
            (order_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_orders(status: str | None = None) -> list:
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def update_order_status(order_id: int, status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id)
        )


def delete_order(order_id: int) -> dict | None:
    """
    Видаляє замовлення та його позиції.
    Повертає dict з даними замовлення перед видаленням або None.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if not row:
            return None
        order = dict(row)
        conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        return order


# ── USER PREFERENCES (стильові вподобання) ──────────────────────────────────

def get_user_preferences(user_id: int) -> dict:
    """Повертає JSON-вподобання з таблиці users."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT preferences FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                return {}
        return {}


def save_user_preferences(user_id: int, prefs: dict):
    """Зберігає JSON-вподобання в таблицю users."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET preferences = ? WHERE user_id = ?",
            (json.dumps(prefs, ensure_ascii=False), user_id)
        )


# ── QUERY INTENTS (збереження розпарсених запитів) ───────────────────────────

def log_query_intent(user_id: int, intent: dict):
    """Зберігає розпарсений інтент з текстового запиту."""
    has_data = any(v is not None for v in intent.values())
    if not has_data:
        return
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO query_intents
               (user_id, category, min_price, max_price, size, color)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, intent.get("category"), intent.get("min_price"),
             intent.get("max_price"), intent.get("size"), intent.get("color"))
        )


def get_query_intent_stats(user_id: int) -> dict:
    """
    Агрегує історію запитів користувача у профіль вподобань.
    Повертає: {categories: {cat: count}, colors: {col: count},
              avg_max_price: float|None, sizes: {size: count}}
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT category, min_price, max_price, size, color "
            "FROM query_intents WHERE user_id = ? "
            "ORDER BY timestamp DESC LIMIT 50",
            (user_id,)
        ).fetchall()

    if not rows:
        return {}

    categories = {}
    colors = {}
    sizes = {}
    prices = []

    for r in rows:
        if r["category"]:
            categories[r["category"]] = categories.get(r["category"], 0) + 1
        if r["color"]:
            colors[r["color"]] = colors.get(r["color"], 0) + 1
        if r["size"]:
            sizes[r["size"]] = sizes.get(r["size"], 0) + 1
        if r["max_price"]:
            prices.append(r["max_price"])
        elif r["min_price"]:
            prices.append(r["min_price"])

    return {
        "categories": categories,
        "colors": colors,
        "sizes": sizes,
        "avg_price": sum(prices) / len(prices) if prices else None,
    }


# ── RESET (для тестування) ───────────────────────────────────────────────────

def reset_user_recommendations(user_id: int) -> dict:
    """
    Скидає всі дані рекомендаційної системи для користувача.
    Повертає dict з кількістю видалених записів по кожній таблиці.
    """
    stats = {}
    with get_connection() as conn:
        # Вподобання (онбординг)
        conn.execute("UPDATE users SET preferences = '{}' WHERE user_id = ?", (user_id,))
        stats["preferences"] = "скинуто"

        # Взаємодії (view, like, cart)
        cur = conn.execute("DELETE FROM interactions WHERE user_id = ?", (user_id,))
        stats["interactions"] = cur.rowcount

        # Інтенти запитів
        cur = conn.execute("DELETE FROM query_intents WHERE user_id = ?", (user_id,))
        stats["query_intents"] = cur.rowcount

        # Вибране
        cur = conn.execute("DELETE FROM favorites WHERE user_id = ?", (user_id,))
        stats["favorites"] = cur.rowcount

        # Сесія (кошик, історія чату)
        conn.execute(
            "INSERT OR REPLACE INTO sessions (user_id, context) VALUES (?, '{}')",
            (user_id,)
        )
        stats["session"] = "скинуто"

    return stats
