"""
admin.py — адмін-панель: товари, замовлення, профіль, скидання.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import SHOP_NAME
from database import (
    get_all_products, get_product_by_id, delete_product, update_product,
    get_all_orders, get_order_items, update_order_status, delete_order,
    get_user_profile, reset_user_recommendations,
)
from handlers.common import (
    is_admin, safe_reply, ORDER_STATUSES, PAGE_SIZE,
)
from handlers.recommendations import _build_profile_text


# ── Команда /admin ───────────────────────────────────────────────────────────

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Немає доступу.")
        return

    keyboard = [
        [InlineKeyboardButton("📋 Список товарів", callback_data="admin_list")],
        [InlineKeyboardButton("📦 Замовлення", callback_data="admin_orders")],
        [InlineKeyboardButton("🗑 Видалити товар за ID", callback_data="admin_delete_prompt")],
        [
            InlineKeyboardButton("👤 Мій профіль", callback_data="admin_profile"),
            InlineKeyboardButton("🔄 Скинути рекомендації", callback_data="admin_reset"),
        ],
    ]
    await safe_reply(
        update.message,
        f"⚙️ *Адмін-панель {SHOP_NAME}*",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Текстовий ввід: видалення товару за ID ───────────────────────────────────

async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обробляє текстовий ввід ID для видалення товару. Повертає True якщо оброблено."""
    user_id = update.effective_user.id
    text = update.message.text

    if not context.user_data.get("awaiting_admin_delete") or not is_admin(user_id):
        return False

    context.user_data["awaiting_admin_delete"] = False
    if text.strip().isdigit():
        pid = int(text.strip())
        p = get_product_by_id(pid)
        if p:
            delete_product(pid)
            await update.message.reply_text(f"✅ Видалено: {p['name']}")
        else:
            await update.message.reply_text(f"Товар з ID {pid} не знайдено.")
    else:
        await update.message.reply_text("ID має бути числом. Спробуй ще: /admin")
    return True


# ── Callbacks ────────────────────────────────────────────────────────────────

async def handle_callback(query, user_id: int, data: str,
                          context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обробляє callback адмін-панелі. Повертає True якщо оброблено."""

    # ── Профіль рекомендацій ─────────────────────────────────────────────
    if data == "admin_profile" and is_admin(user_id):
        text = _build_profile_text(user_id)
        await safe_reply(query.message, text)
        return True

    # ── Скидання рекомендацій ────────────────────────────────────────────
    if data == "admin_reset" and is_admin(user_id):
        stats = reset_user_recommendations(user_id)
        lines = [
            "🔄 *Рекомендаційну систему скинуто:*\n",
            f"• Вподобання (онбординг): {stats['preferences']}",
            f"• Взаємодії (view/like/cart): {stats['interactions']} записів",
            f"• Інтенти запитів: {stats['query_intents']} записів",
            f"• Вибране: {stats['favorites']} записів",
            f"• Сесія (кошик, чат): {stats['session']}",
        ]
        await safe_reply(query.message, "\n".join(lines))
        return True

    # ── Список товарів з пагінацією ──────────────────────────────────────
    if (data == "admin_list" or data.startswith("admlp_")) and is_admin(user_id):
        page = 0
        if data.startswith("admlp_"):
            page = int(data[6:])

        products = get_all_products(in_stock_only=False)
        if not products:
            await query.message.reply_text("Товарів немає.")
            return True

        total = len(products)
        total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        start = page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_items = products[start:end]

        await query.message.reply_text(
            f"📋 *Товари* (сторінка {page + 1}/{total_pages}, всього {total}):",
            parse_mode=ParseMode.MARKDOWN,
        )

        for p in page_items:
            status = "✅" if p["in_stock"] else "❌"
            keyboard = [[
                InlineKeyboardButton("🗑 Видалити", callback_data=f"admin_del_{p['id']}"),
                InlineKeyboardButton(f"{status} Наявність", callback_data=f"admin_toggle_{p['id']}"),
            ]]
            await safe_reply(
                query.message,
                f"ID {p['id']} | *{p['name']}*\n{p['brand']} | {p['price']} грн | {status}",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ Назад", callback_data=f"admlp_{page - 1}")
                )
            nav_buttons.append(
                InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop")
            )
            if page < total_pages - 1:
                nav_buttons.append(
                    InlineKeyboardButton("Далі ➡️", callback_data=f"admlp_{page + 1}")
                )
            await query.message.reply_text(
                "Навігація:",
                reply_markup=InlineKeyboardMarkup([nav_buttons]),
            )
        return True

    # ── Видалення товару (по кнопці) ─────────────────────────────────────
    if data == "admin_delete_prompt" and is_admin(user_id):
        context.user_data["awaiting_admin_delete"] = True
        await query.message.reply_text("Введіть ID товару для видалення:")
        return True

    if data.startswith("admin_del_") and is_admin(user_id):
        pid = int(data[10:])
        p = get_product_by_id(pid)
        if p:
            delete_product(pid)
            await query.message.reply_text(f"✅ Видалено: {p['name']}")
        return True

    # ── Переключення наявності ───────────────────────────────────────────
    if data.startswith("admin_toggle_") and is_admin(user_id):
        pid = int(data[13:])
        p = get_product_by_id(pid)
        if p:
            new_status = 0 if p["in_stock"] else 1
            update_product(pid, in_stock=new_status)
            label = "в наявності ✅" if new_status else "відсутній ❌"
            await query.answer(f"Статус: {label}", show_alert=True)
        return True

    # ── Замовлення з пагінацією ──────────────────────────────────────────
    if (data == "admin_orders" or data.startswith("admop_")) and is_admin(user_id):
        page = 0
        if data.startswith("admop_"):
            page = int(data[6:])

        orders = get_all_orders()
        if not orders:
            await query.message.reply_text("Замовлень немає.")
            return True

        total = len(orders)
        total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        start = page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_orders = orders[start:end]

        await query.message.reply_text(
            f"📦 *Замовлення* (сторінка {page + 1}/{total_pages}, всього {total}):",
            parse_mode=ParseMode.MARKDOWN,
        )

        for order in page_orders:
            status_label = ORDER_STATUSES.get(order["status"], order["status"])
            items = get_order_items(order["id"])
            item_lines = [f"  • {it['product_name']} ×{it['quantity']}" for it in items]

            profile = get_user_profile(order["user_id"])
            client_info = ""
            if profile:
                client_info = f"👤 {profile['first_name']} {profile['last_name']} | 📱 {profile['phone']}\n"

            status_buttons = []
            for status_key, status_label_btn in ORDER_STATUSES.items():
                if status_key != order["status"]:
                    status_buttons.append(
                        InlineKeyboardButton(
                            status_label_btn[:15],
                            callback_data=f"ordst_{order['id']}_{status_key}",
                        )
                    )

            keyboard = []
            for i in range(0, len(status_buttons), 3):
                keyboard.append(status_buttons[i:i + 3])
            keyboard.append([
                InlineKeyboardButton(
                    "🗑 Видалити замовлення",
                    callback_data=f"orddel_{order['id']}",
                ),
            ])

            await safe_reply(
                query.message,
                f"📦 *{order['order_code']}*\n"
                f"{client_info}"
                f"Статус: {ORDER_STATUSES.get(order['status'], order['status'])}\n"
                f"Сума: {order['total']:.0f} грн\n"
                + "\n".join(item_lines),
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            )

        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ Назад", callback_data=f"admop_{page - 1}")
                )
            nav_buttons.append(
                InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop")
            )
            if page < total_pages - 1:
                nav_buttons.append(
                    InlineKeyboardButton("Далі ➡️", callback_data=f"admop_{page + 1}")
                )
            await query.message.reply_text(
                "Навігація:",
                reply_markup=InlineKeyboardMarkup([nav_buttons]),
            )
        return True

    # ── Зміна статусу замовлення ─────────────────────────────────────────
    if data.startswith("ordst_") and is_admin(user_id):
        parts = data.split("_")
        order_id = int(parts[1])
        new_status = parts[2]
        update_order_status(order_id, new_status)
        status_label = ORDER_STATUSES.get(new_status, new_status)
        await query.answer(f"Статус змінено: {status_label}", show_alert=True)

        from database import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, order_code FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
        if row:
            try:
                await context.application.bot.send_message(
                    chat_id=row["user_id"],
                    text=f"📦 Статус замовлення *{row['order_code']}* змінено:\n{status_label}",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass
        return True

    # ── Підтвердження видалення замовлення ────────────────────────────────
    if data.startswith("orddel_") and is_admin(user_id):
        order_id = int(data[7:])
        await query.message.reply_text(
            f"⚠️ Ви впевнені, що хочете видалити замовлення ID {order_id}?\n"
            f"Цю дію неможливо скасувати.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Так, видалити",
                        callback_data=f"orddelok_{order_id}",
                    ),
                    InlineKeyboardButton("❌ Скасувати", callback_data="noop"),
                ],
            ]),
        )
        return True

    if data.startswith("orddelok_") and is_admin(user_id):
        order_id = int(data[9:])
        deleted = delete_order(order_id)
        if deleted:
            await query.message.edit_text(
                f"✅ Замовлення *{deleted['order_code']}* видалено.",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await query.message.edit_text("Замовлення не знайдено.")
        return True

    return False
