"""
cart.py — кошик, оформлення замовлення, реєстрація профілю.
"""
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import PAYMENT_DETAILS, ORDERS_CHAT_ID
from database import (
    get_session, update_session, get_product_by_id,
    log_interaction, get_user_profile, save_user_profile,
    create_order,
)
from handlers.common import safe_reply, ORDER_STATUSES
import logging

logger = logging.getLogger(__name__)


# ── Команда /cart ────────────────────────────────────────────────────────────

async def cart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    cart = session.get("cart", {})

    if not cart:
        await update.message.reply_text(
            "🛒 Кошик порожній.\nПерегляньте /catalog або напишіть що шукаєте!"
        )
        return

    total = 0
    lines = []
    keyboard = []

    for pid_str, qty in cart.items():
        p = get_product_by_id(int(pid_str))
        if p:
            subtotal = p["price"] * qty
            total += subtotal
            lines.append(f"• *{p['name']}* ×{qty} — {subtotal:.0f} грн")
            keyboard.append([
                InlineKeyboardButton("➖", callback_data=f"cart_minus_{pid_str}"),
                InlineKeyboardButton(f"{p['name'][:20]} ×{qty}", callback_data="noop"),
                InlineKeyboardButton("➕", callback_data=f"cart_plus_{pid_str}"),
                InlineKeyboardButton("🗑", callback_data=f"cart_delete_{pid_str}"),
            ])

    keyboard.append([InlineKeyboardButton("🗑 Очистити кошик", callback_data="cart_clear")])
    keyboard.append([InlineKeyboardButton("✅ Оформити замовлення", callback_data="cart_checkout")])

    await safe_reply(
        update.message,
        "🛒 *Ваш кошик:*\n\n" + "\n".join(lines) + f"\n\n💰 *Разом: {total:.0f} грн*",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Реєстрація (обробка кроків) ─────────────────────────────────────────────

async def handle_registration_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обробляє кроки реєстрації. Повертає True якщо оброблено."""
    reg_step = context.user_data.get("registration_step")
    if not reg_step:
        return False

    user = update.effective_user
    text = update.message.text

    if reg_step == "first_name":
        context.user_data["reg_first_name"] = text.strip()
        context.user_data["registration_step"] = "last_name"
        await update.message.reply_text("Введіть ваше *прізвище*:", parse_mode=ParseMode.MARKDOWN)
        return True

    if reg_step == "last_name":
        context.user_data["reg_last_name"] = text.strip()
        context.user_data["registration_step"] = "phone"
        await update.message.reply_text("Введіть ваш *номер телефону*:", parse_mode=ParseMode.MARKDOWN)
        return True

    if reg_step == "phone":
        phone = text.strip()
        digits = re.sub(r"[^\d]", "", phone)
        if len(digits) < 10 or len(digits) > 15:
            await update.message.reply_text(
                "❌ Номер телефону має містити від 10 до 15 цифр.\n"
                "Приклад: +380991234567 або 0991234567\n\n"
                "Введіть номер ще раз:"
            )
            return True
        context.user_data["reg_phone"] = phone
        context.user_data["registration_step"] = "address"
        await update.message.reply_text(
            "Введіть *адресу доставки*\n(місто, відділення Нової Пошти або адресу):",
            parse_mode=ParseMode.MARKDOWN,
        )
        return True

    if reg_step == "address":
        context.user_data["reg_address"] = text.strip()
        context.user_data["registration_step"] = None

        save_user_profile(
            user.id,
            context.user_data.get("reg_first_name", ""),
            context.user_data.get("reg_last_name", ""),
            context.user_data.get("reg_phone", ""),
            context.user_data.get("reg_address", ""),
        )

        source = context.user_data.get("registration_source")
        await update.message.reply_text("✅ Дані збережено!")

        if source == "checkout":
            context.user_data["registration_source"] = None
            await _show_order_confirmation(update.message, user.id)
        return True

    return False


async def _show_order_confirmation(message, user_id: int):
    """Показує підтвердження замовлення з даними профілю."""
    session = get_session(user_id)
    cart = session.get("cart", {})
    if not cart:
        await message.reply_text("🛒 Кошик порожній.")
        return

    profile = get_user_profile(user_id)
    total = 0
    lines = []
    for pid_str, qty in cart.items():
        p = get_product_by_id(int(pid_str))
        if p:
            subtotal = p["price"] * qty
            total += subtotal
            lines.append(f"• {p['name']} ×{qty} — {subtotal:.0f} грн")

    await safe_reply(
        message,
        f"📋 *Підтвердження замовлення:*\n\n"
        + "\n".join(lines) +
        f"\n\n💰 *Разом: {total:.0f} грн*\n\n"
        f"👤 {profile['first_name']} {profile['last_name']}\n"
        f"📱 {profile['phone']}\n"
        f"📍 {profile['delivery_address']}\n\n"
        f"Все вірно?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Підтверджую", callback_data="confirm_order"),
                InlineKeyboardButton("✏️ Змінити дані", callback_data="edit_profile"),
            ],
        ]),
    )


# ── Callbacks ────────────────────────────────────────────────────────────────

async def handle_callback(query, user_id: int, data: str,
                          context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обробляє callback-запити кошика. Повертає True якщо оброблено."""

    # ── Додати в кошик ───────────────────────────────────────────────────
    if data.startswith("cart_add_"):
        pid = int(data[9:])
        session = get_session(user_id)
        cart = session.get("cart", {})
        cart[str(pid)] = cart.get(str(pid), 0) + 1
        session["cart"] = cart
        update_session(user_id, session)
        log_interaction(user_id, pid, "cart")

        p = get_product_by_id(pid)
        name = p["name"] if p else "Товар"
        total_qty = cart[str(pid)]
        await query.answer(f"✅ {name} додано! (×{total_qty})", show_alert=False)
        return True

    # ── Кошик: + ─────────────────────────────────────────────────────────
    if data.startswith("cart_plus_"):
        pid_str = data[10:]
        session = get_session(user_id)
        cart = session.get("cart", {})
        cart[pid_str] = cart.get(pid_str, 0) + 1
        session["cart"] = cart
        update_session(user_id, session)
        await query.answer(f"Кількість: {cart[pid_str]}", show_alert=False)
        await query.message.reply_text("Оновлено! /cart — переглянути кошик.")
        return True

    # ── Кошик: - ─────────────────────────────────────────────────────────
    if data.startswith("cart_minus_"):
        pid_str = data[11:]
        session = get_session(user_id)
        cart = session.get("cart", {})
        if pid_str in cart:
            cart[pid_str] = max(0, cart[pid_str] - 1)
            if cart[pid_str] == 0:
                del cart[pid_str]
        session["cart"] = cart
        update_session(user_id, session)
        await query.answer("Кількість зменшено", show_alert=False)
        await query.message.reply_text("Оновлено! /cart — переглянути кошик.")
        return True

    # ── Кошик: видалити позицію ──────────────────────────────────────────
    if data.startswith("cart_delete_"):
        pid_str = data[12:]
        session = get_session(user_id)
        cart = session.get("cart", {})
        cart.pop(pid_str, None)
        session["cart"] = cart
        update_session(user_id, session)
        await query.answer("Товар видалено", show_alert=False)
        await query.message.reply_text("Видалено з кошика. /cart — переглянути.")
        return True

    # ── Кошик: очистити ──────────────────────────────────────────────────
    if data == "cart_clear":
        session = get_session(user_id)
        session["cart"] = {}
        update_session(user_id, session)
        await query.message.edit_text("🛒 Кошик очищено.")
        return True

    # ── Кошик: показати (callback з AI-відповіді) ────────────────────────
    if data == "show_cart":
        session = get_session(user_id)
        cart = session.get("cart", {})
        if not cart:
            await query.message.reply_text(
                "🛒 Кошик порожній.\nПерегляньте /catalog або напишіть що шукаєте!"
            )
        else:
            await query.message.reply_text("Щоб переглянути кошик, натисни /cart")
        return True

    # ── Оформити замовлення ──────────────────────────────────────────────
    if data == "cart_checkout":
        profile = get_user_profile(user_id)
        if not profile:
            context.user_data["registration_step"] = "first_name"
            context.user_data["registration_source"] = "checkout"
            await query.message.reply_text(
                "📝 Для оформлення замовлення потрібні ваші дані.\n\n"
                "Введіть ваше *ім'я*:",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await _show_order_confirmation(query.message, user_id)
        return True

    # ── Підтвердження замовлення ─────────────────────────────────────────
    if data == "confirm_order":
        session = get_session(user_id)
        cart = session.get("cart", {})
        if not cart:
            await query.message.reply_text("🛒 Кошик порожній.")
            return True

        order = create_order(user_id, cart)
        if not order:
            await query.message.reply_text("Помилка при створенні замовлення.")
            return True

        session["cart"] = {}
        update_session(user_id, session)

        await safe_reply(
            query.message,
            f"✅ *Замовлення створено!*\n\n"
            f"🔖 Код замовлення: *{order['order_code']}*\n"
            f"💰 Сума: *{order['total']:.0f} грн*\n\n"
            f"💳 *Реквізити для оплати:*\n{PAYMENT_DETAILS}\n\n"
            f"📝 В коментарях до оплати вкажіть код: *{order['order_code']}*\n\n"
            f"Після оплати ми перевіримо транзакцію та підтвердимо замовлення.\n"
            f"Статус можна перевірити: /orders",
        )

        # Повідомлення адміну
        profile = get_user_profile(user_id)
        profile_info = ""
        if profile:
            profile_info = (
                f"👤 {profile['first_name']} {profile['last_name']}\n"
                f"📱 {profile['phone']}\n"
                f"📍 {profile['delivery_address']}\n"
            )

        item_lines = [f"  • {it['name']} ×{it['quantity']} — {it['price']:.0f} грн"
                      for it in order["items"]]

        admin_text = (
            f"🆕 *Нове замовлення!*\n\n"
            f"🔖 {order['order_code']}\n"
            f"{profile_info}"
            f"💰 Сума: {order['total']:.0f} грн\n\n"
            + "\n".join(item_lines)
        )

        try:
            await context.application.bot.send_message(
                chat_id=ORDERS_CHAT_ID,
                text=admin_text,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error("Не вдалося надіслати замовлення в чат %s: %s", ORDERS_CHAT_ID, e)
        return True

    # ── Редагування профілю ──────────────────────────────────────────────
    if data == "edit_profile":
        context.user_data["registration_step"] = "first_name"
        context.user_data["registration_source"] = "checkout"
        await query.message.reply_text(
            "📝 Введіть ваше *ім'я*:",
            parse_mode=ParseMode.MARKDOWN,
        )
        return True

    return False
