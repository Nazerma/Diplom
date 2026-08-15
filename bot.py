"""
bot.py — головний файл Telegram-бота Nazerva

Точка входу, реєстрація handlers, маршрутизація callbacks і текстових повідомлень.
Вся бізнес-логіка винесена в модулі handlers/*.
"""
import logging
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)

from config import TELEGRAM_TOKEN, GEMINI_API_KEY, SHOP_NAME
from database import (
    init_db, migrate_db, get_or_create_user, get_session, update_session,
    get_product_by_id, search_products, get_user_preferences,
)
from gemini import process_message

from handlers.common import (
    safe_reply, main_keyboard, send_products_page,
    _last_ai_call, AI_COOLDOWN,
)

from handlers import catalog, cart, favorites, orders, recommendations, admin

# ── Логування ────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  КОМАНДИ
# ══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.first_name or "")

    session = get_session(user.id)
    if "cart" not in session:
        session["cart"] = {}
        update_session(user.id, session)

    await safe_reply(
        update.message,
        f"👋 Привіт, *{user.first_name}*! Ласкаво просимо до *{SHOP_NAME}*!\n\n"
        f"Я — AI-асистент магазину. Можу:\n"
        f"• Знайти одяг за твоїм описом\n"
        f"• Підібрати товари під твій стиль\n"
        f"• Допомогти з вибором розміру та кольору\n\n"
        f"Просто напиши що шукаєш, або скористайся меню 👇",
        reply_markup=main_keyboard(),
    )

    prefs = get_user_preferences(user.id)
    if not prefs.get("onboarding_done"):
        await update.message.reply_text(
            "🎨 Хочеш, щоб я краще підбирав одяг для тебе?\n"
            "Пройди коротке опитування — це займе 30 секунд!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Пройти опитування", callback_data="onb_start")],
                [InlineKeyboardButton("⏭ Пропустити", callback_data="onb_skip")],
            ]),
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(
        update.message,
        f"*{SHOP_NAME} — Довідка*\n\n"
        f"*Команди:*\n"
        f"/start — Головне меню\n"
        f"/catalog — Каталог категорій\n"
        f"/filter — Підбір товару за параметрами\n"
        f"/recommendations — Рекомендації для тебе\n"
        f"/style — Налаштувати стильові вподобання\n"
        f"/profile — Профіль рекомендацій\n"
        f"/cart — Кошик\n"
        f"/favorites — Вибране\n"
        f"/orders — Мої замовлення\n"
        f"/help — Ця довідка\n\n"
        f"*Або просто напиши:*\n"
        f"«Шукаю теплу куртку до 3000 грн»\n"
        f"«Хочу чорні кросівки розмір 42»\n"
        f"«Покажи светри бежевого кольору»\n\n"
        f"Чим більше ти шукаєш та лайкаєш — тим точніші рекомендації 🤖",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  МАРШРУТИЗАТОР CALLBACK-ЗАПИТІВ
# ══════════════════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "noop":
        return

    # Делегуємо кожному модулю по черзі
    if await recommendations.handle_callback(query, user_id, data, context):
        return
    if await catalog.handle_callback(query, user_id, data, context):
        return
    if await cart.handle_callback(query, user_id, data, context):
        return
    if await favorites.handle_callback(query, user_id, data, context):
        return
    if await admin.handle_callback(query, user_id, data, context):
        return


# ══════════════════════════════════════════════════════════════════════════════
#  ОБРОБКА ТЕКСТОВИХ ПОВІДОМЛЕНЬ
# ══════════════════════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    # ── Кнопки постійного меню ────────────────────────────────────────────
    menu_map = {
        "🛍 Каталог":       catalog.catalog_command,
        "🛒 Кошик":         cart.cart_command,
        "❓ Допомога":      help_command,
        "🎯 Підбір товару": catalog.filter_command,
        "💡 Для мене":      recommendations.recommendations_command,
        "❤️ Вибране":       favorites.favorites_command,
        "📦 Замовлення":    orders.orders_command,
    }
    if text in menu_map:
        await menu_map[text](update, context)
        return

    # ── Реєстрація (збір даних) ──────────────────────────────────────────
    if await cart.handle_registration_step(update, context):
        return

    # ── Адмін: видалення товару за ID ────────────────────────────────────
    if await admin.handle_admin_text(update, context):
        return

    # ── Режим текстового пошуку ──────────────────────────────────────────
    if context.user_data.get("awaiting_search"):
        context.user_data["awaiting_search"] = False
        products = search_products(query=text)
        if products:
            await send_products_page(
                update.message, products, user.id,
                page=0,
                prefix=f"🔍 Знайдено {len(products)} товарів за запитом «{text}»:",
                context=context,
                list_key="search_results",
            )
        else:
            await update.message.reply_text(
                f"Нічого не знайдено за запитом «{text}».\n"
                f"Спробуйте інші слова або перегляньте /catalog"
            )
        return

    # ── Rate limiting ────────────────────────────────────────────────────
    now = time.time()
    if now - _last_ai_call[user.id] < AI_COOLDOWN:
        await update.message.reply_text("Зачекай кілька секунд перед наступним запитом ⏳")
        return
    _last_ai_call[user.id] = now

    # ── RAG: Gemini + CBF ────────────────────────────────────────────────
    await update.message.chat.send_action("typing")

    try:
        result = await process_message(user.id, text)
    except Exception as e:
        logger.error("Gemini error: %s", e)
        result = {
            "reply": "Вибачте, сталася технічна помилка. "
                     "Спробуйте ще раз або скористайтесь /catalog 🙏",
            "product_ids": [],
        }

    reply_text = result["reply"]
    product_ids = result.get("product_ids", [])

    keyboard = []
    for pid in product_ids[:5]:
        p = get_product_by_id(pid)
        if p:
            keyboard.append([
                InlineKeyboardButton(
                    f"🛒 {p['name'][:30]} — {p['price']:.0f} грн",
                    callback_data=f"cart_add_{pid}",
                ),
                InlineKeyboardButton("❤️", callback_data=f"like_{pid}"),
                InlineKeyboardButton("📋", callback_data=f"detail_{pid}"),
            ])

    keyboard.append([
        InlineKeyboardButton("🛍 Каталог", callback_data="cat_футболки"),
        InlineKeyboardButton("🛒 Кошик",   callback_data="show_cart"),
    ])

    await safe_reply(
        update.message,
        reply_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_TOKEN is not configured. Check .env.")
        return
    if not GEMINI_API_KEY:
        print("WARNING: GEMINI_API_KEY is not configured; local fallback replies will be used.")

    init_db()
    migrate_db()
    logger.info("База даних ініціалізована")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",           start))
    app.add_handler(CommandHandler("help",            help_command))
    app.add_handler(CommandHandler("catalog",         catalog.catalog_command))
    app.add_handler(CommandHandler("filter",          catalog.filter_command))
    app.add_handler(CommandHandler("search",          catalog.search_command))
    app.add_handler(CommandHandler("recommendations", recommendations.recommendations_command))
    app.add_handler(CommandHandler("style",           recommendations.style_command))
    app.add_handler(CommandHandler("reset",           recommendations.reset_command))
    app.add_handler(CommandHandler("profile",         recommendations.profile_command))
    app.add_handler(CommandHandler("cart",            cart.cart_command))
    app.add_handler(CommandHandler("favorites",       favorites.favorites_command))
    app.add_handler(CommandHandler("orders",          orders.orders_command))
    app.add_handler(CommandHandler("admin",           admin.admin_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот %s запущено!", SHOP_NAME)
    print(f"{SHOP_NAME} bot is running. Press Ctrl+C to stop.")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
