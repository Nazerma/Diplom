"""
orders.py — замовлення користувача.
"""
from telegram import Update
from telegram.ext import ContextTypes

from database import get_user_orders, get_order_items
from handlers.common import safe_reply, ORDER_STATUSES


async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    orders = get_user_orders(user_id)

    if not orders:
        await update.message.reply_text(
            "📦 У вас поки немає замовлень.\n"
            "Додайте товари в кошик та оформіть замовлення!"
        )
        return

    for order in orders[:10]:
        status_label = ORDER_STATUSES.get(order["status"], order["status"])
        items = get_order_items(order["id"])
        item_lines = [f"  • {it['product_name']} ×{it['quantity']}" for it in items]

        await safe_reply(
            update.message,
            f"📦 *Замовлення {order['order_code']}*\n"
            f"Статус: {status_label}\n"
            f"Сума: {order['total']:.0f} грн\n"
            f"Дата: {order['created_at']}\n\n"
            + "\n".join(item_lines),
        )
