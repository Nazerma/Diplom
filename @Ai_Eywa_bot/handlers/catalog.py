"""
catalog.py — каталог, пошук, фільтрація, детальна картка, пагінація.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import get_categories, search_products, get_product_by_id
from handlers.common import (
    safe_reply, product_detail_text, product_buttons,
    send_products_page,
)


# ── Команди ──────────────────────────────────────────────────────────────────

async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import SHOP_NAME
    categories = get_categories()
    keyboard = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(cat.capitalize(), callback_data=f"cat_{cat}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await safe_reply(
        update.message,
        f"📦 *Каталог {SHOP_NAME}*\nОберіть категорію:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_search"] = True
    await update.message.reply_text("🔍 Введіть назву товару, бренд або ключове слово:")


async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories = get_categories()
    keyboard = [
        [InlineKeyboardButton(c.capitalize(), callback_data=f"fcat_{c}")]
        for c in categories
    ]
    keyboard.append([InlineKeyboardButton("⏭ Без категорії", callback_data="fcat_skip")])

    await safe_reply(
        update.message,
        "🎯 *Підбір товару*\n\nКрок 1: оберіть категорію:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Callbacks ────────────────────────────────────────────────────────────────

async def handle_callback(query, user_id: int, data: str,
                          context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обробляє callback-запити каталогу. Повертає True якщо оброблено."""

    # ── Категорія каталогу ────────────────────────────────────────────────
    if data.startswith("cat_"):
        category = data[4:]
        products = search_products(category=category)
        if not products:
            await query.message.reply_text(f"У категорії «{category}» немає товарів.")
            return True
        await send_products_page(
            query.message, products, user_id,
            page=0,
            prefix=f"📦 Категорія: *{category.capitalize()}*  ({len(products)} товарів)",
            context=context,
            list_key=f"cat_{category}",
        )
        return True

    # ── Пагінація ────────────────────────────────────────────────────────
    if data.startswith("page_"):
        parts = data.split("_")
        page_num = int(parts[-1])
        list_key = "_".join(parts[1:-1])

        product_ids = context.user_data.get(list_key, [])
        if not product_ids:
            await query.message.reply_text("Список товарів не знайдено. Спробуйте ще раз.")
            return True

        products = [get_product_by_id(pid) for pid in product_ids]
        products = [p for p in products if p]

        await send_products_page(
            query.message, products, user_id,
            page=page_num,
            context=context,
            list_key=list_key,
        )
        return True

    # ── Детальна картка товару ────────────────────────────────────────────
    if data.startswith("detail_"):
        pid = int(data[7:])
        p = get_product_by_id(pid)
        if not p:
            await query.message.reply_text("Товар не знайдено.")
            return True

        buttons = product_buttons(pid, user_id)
        image_url = p.get("image_url", "")

        if image_url:
            try:
                await query.message.reply_photo(
                    photo=image_url,
                    caption=product_detail_text(p),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=buttons,
                )
                return True
            except Exception:
                pass

        await safe_reply(query.message, product_detail_text(p), reply_markup=buttons)
        return True

    # ── Фільтр: вибір категорії ──────────────────────────────────────────
    if data.startswith("fcat_"):
        cat = None if data == "fcat_skip" else data[5:]
        context.user_data["filter_category"] = cat

        keyboard = [
            [InlineKeyboardButton("до 1000 грн",    callback_data="fprice_0_1000")],
            [InlineKeyboardButton("1000–3000 грн",  callback_data="fprice_1000_3000")],
            [InlineKeyboardButton("3000–6000 грн",  callback_data="fprice_3000_6000")],
            [InlineKeyboardButton("понад 6000 грн", callback_data="fprice_6000_99999")],
            [InlineKeyboardButton("⏭ Будь-яка ціна", callback_data="fprice_skip")],
        ]
        await query.message.reply_text(
            "Крок 2: оберіть ціновий діапазон:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True

    # ── Фільтр: вибір ціни ───────────────────────────────────────────────
    if data.startswith("fprice_"):
        parts = data[7:].split("_")
        min_p = max_p = None
        if parts[0] != "skip":
            min_p = int(parts[0])
            max_p = int(parts[1])
        context.user_data["filter_min_price"] = min_p
        context.user_data["filter_max_price"] = max_p

        category = context.user_data.get("filter_category")
        if category == "взуття":
            sizes = ["36", "37", "38", "39", "40", "41", "42", "43", "44", "45"]
            keyboard = [
                [InlineKeyboardButton(s, callback_data=f"fsize_{s}") for s in sizes[:5]],
                [InlineKeyboardButton(s, callback_data=f"fsize_{s}") for s in sizes[5:]],
            ]
        else:
            sizes = ["XS", "S", "M", "L", "XL", "XXL"]
            keyboard = [
                [InlineKeyboardButton(s, callback_data=f"fsize_{s}") for s in sizes[:3]],
                [InlineKeyboardButton(s, callback_data=f"fsize_{s}") for s in sizes[3:]],
            ]
        keyboard.append([InlineKeyboardButton("⏭ Будь-який розмір", callback_data="fsize_skip")])
        await query.message.reply_text(
            "Крок 3: оберіть розмір:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True

    # ── Фільтр: вибір розміру → результат ────────────────────────────────
    if data.startswith("fsize_"):
        size = None if data == "fsize_skip" else data[6:]
        category  = context.user_data.get("filter_category")
        min_price = context.user_data.get("filter_min_price")
        max_price = context.user_data.get("filter_max_price")

        products = search_products(
            category=category, min_price=min_price,
            max_price=max_price, size=size,
        )

        if not products:
            await query.message.reply_text(
                "За вашими параметрами нічого не знайдено. Спробуйте ширший пошук."
            )
            return True

        await send_products_page(
            query.message, products, user_id,
            page=0,
            prefix=f"🎯 Знайдено {len(products)} товарів за вашим фільтром:",
            context=context,
            list_key="filter_results",
        )
        return True

    return False
