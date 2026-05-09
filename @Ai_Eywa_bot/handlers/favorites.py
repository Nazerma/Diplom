"""
favorites.py — вибране (лайки).
"""
from telegram import Update
from telegram.ext import ContextTypes

from database import get_favorites, toggle_favorite, log_interaction
from handlers.common import send_products_page


# ── Команда /favorites ──────────────────────────────────────────────────────

async def favorites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    favs = get_favorites(user_id)

    if not favs:
        await update.message.reply_text(
            "❤️ У вибраному поки порожньо.\n"
            "Натискай ❤️ на товарах щоб додати їх сюди!"
        )
        return

    await send_products_page(
        update.message, favs, user_id,
        page=0,
        prefix=f"❤️ *Вибране* ({len(favs)} товарів):",
        context=context,
        list_key="favorites_list",
    )


# ── Callbacks ────────────────────────────────────────────────────────────────

async def handle_callback(query, user_id: int, data: str,
                          context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обробляє callback лайків. Повертає True якщо оброблено."""
    if data.startswith("like_"):
        pid = int(data[5:])
        added = toggle_favorite(user_id, pid)
        if added:
            log_interaction(user_id, pid, "like")
            await query.answer("❤️ Додано до вибраного!", show_alert=False)
        else:
            await query.answer("💔 Видалено з вибраного.", show_alert=False)
        return True

    return False
