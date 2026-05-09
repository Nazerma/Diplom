"""
common.py — спільні утиліти, константи та клавіатури.
Імпортується усіма модулями handlers/*.
"""
import json
import logging
from collections import defaultdict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS
from database import is_favorite, log_interaction

logger = logging.getLogger(__name__)

# ── Константи ────────────────────────────────────────────────────────────────
PAGE_SIZE = 5
AI_COOLDOWN = 3.0
_last_ai_call: dict[int, float] = defaultdict(float)

ORDER_STATUSES = {
    "pending":    "⏳ Очікує оплати",
    "paid":       "💳 Оплачено",
    "processing": "📦 В обробці",
    "shipped":    "🚚 Відправлено",
    "delivered":  "✅ Доставлено",
    "cancelled":  "❌ Скасовано",
}


# ── Допоміжні функції ────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def main_keyboard():
    return ReplyKeyboardMarkup(
        [["🛍 Каталог", "🎯 Підбір товару"],
         ["💡 Для мене", "❤️ Вибране"],
         ["🛒 Кошик", "📦 Замовлення"],
         ["❓ Допомога"]],
        resize_keyboard=True,
    )


async def safe_reply(message, text: str, reply_markup=None):
    """Відправляє повідомлення з Markdown, з фолбеком на plain text."""
    try:
        await message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )
    except Exception:
        await message.reply_text(text, reply_markup=reply_markup)


def product_card_text(p: dict) -> str:
    try:
        sizes = json.loads(p["sizes"]) if isinstance(p["sizes"], str) else p["sizes"]
        colors = json.loads(p["colors"]) if isinstance(p["colors"], str) else p["colors"]
    except Exception:
        sizes, colors = [], []

    return (
        f"🏷 *{p['name']}*\n"
        f"📦 {p['brand']}  |  💰 {p['price']:.0f} грн\n"
        f"📐 {', '.join(sizes)}\n"
        f"🎨 {', '.join(colors)}\n"
        f"🧵 {p['material']}"
    )


def product_detail_text(p: dict) -> str:
    try:
        sizes = json.loads(p["sizes"]) if isinstance(p["sizes"], str) else p["sizes"]
        colors = json.loads(p["colors"]) if isinstance(p["colors"], str) else p["colors"]
    except Exception:
        sizes, colors = [], []

    desc = p.get("description", "")
    stock = "✅ В наявності" if p.get("in_stock") else "❌ Немає в наявності"

    return (
        f"🏷 *{p['name']}*\n\n"
        f"📦 Бренд: {p['brand']}\n"
        f"💰 Ціна: {p['price']:.0f} грн\n"
        f"📐 Розміри: {', '.join(sizes)}\n"
        f"🎨 Кольори: {', '.join(colors)}\n"
        f"🧵 Матеріал: {p['material']}\n"
        f"📋 {desc}\n\n"
        f"{stock}"
    )


def product_buttons(product_id: int, user_id: int) -> InlineKeyboardMarkup:
    fav = is_favorite(user_id, product_id)
    heart = "💔 Прибрати" if fav else "❤️ Лайк"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛒 В кошик", callback_data=f"cart_add_{product_id}"),
            InlineKeyboardButton(heart, callback_data=f"like_{product_id}"),
        ],
        [
            InlineKeyboardButton("📋 Детальніше", callback_data=f"detail_{product_id}"),
        ],
    ])


async def send_product_card(target, p: dict, user_id: int):
    """Відправляє картку товару — з фото якщо є, або текстом."""
    image_url = p.get("image_url", "")
    buttons = product_buttons(p["id"], user_id)

    if image_url:
        try:
            await target.reply_photo(
                photo=image_url,
                caption=product_card_text(p),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=buttons,
            )
            return
        except Exception as e:
            logger.warning("Не вдалося надіслати фото для %s: %s", p["name"], e)

    await safe_reply(target, product_card_text(p), reply_markup=buttons)


async def send_products_page(target, products: list, user_id: int,
                             page: int = 0, prefix: str = "",
                             context: ContextTypes.DEFAULT_TYPE = None,
                             list_key: str = "product_list"):
    """Відправляє сторінку товарів з пагінацією."""
    total = len(products)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = products[start:end]

    if prefix and page == 0:
        await safe_reply(target, prefix)

    for p in page_items:
        await send_product_card(target, p, user_id)
        log_interaction(user_id, p["id"], "view")

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{list_key}_{page - 1}")
            )
        nav_buttons.append(
            InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop")
        )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton("Далі ➡️", callback_data=f"page_{list_key}_{page + 1}")
            )
        await target.reply_text(
            f"📄 Сторінка {page + 1} з {total_pages} (всього {total} товарів)",
            reply_markup=InlineKeyboardMarkup([nav_buttons]),
        )

    if context:
        context.user_data[list_key] = [p["id"] for p in products]
