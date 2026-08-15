"""
recommendations.py — рекомендації, онбординг (анкета стилю),
                     профіль користувача, скидання.
"""
from collections import Counter

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import (
    get_user_preferences, save_user_preferences,
    reset_user_recommendations,
    get_user_interactions, get_query_intent_stats,
)
from recommender import get_recommendations, build_user_profile, CATEGORIES, BRANDS
from handlers.common import safe_reply, send_products_page


# ── Команди ──────────────────────────────────────────────────────────────────

async def recommendations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    prefs = get_user_preferences(user_id)

    recs = get_recommendations(user_id, top_n=10)

    if not recs:
        if not prefs.get("onboarding_done"):
            await update.message.reply_text(
                "💡 Щоб рекомендації працювали краще, пройди коротке опитування!\n"
                "А також переглядай товари, лайкай та додавай у кошик — я навчуся.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎨 Пройти опитування", callback_data="onb_start")],
                ]),
            )
        else:
            await update.message.reply_text(
                "💡 Поки що недостатньо даних для рекомендацій.\n"
                "Переглядай товари, лайкай та додавай у кошик — я навчуся!"
            )
        return

    sources = []
    if prefs.get("onboarding_done"):
        style_labels = {"sport": "спортивний", "casual": "casual",
                        "classic": "класичний", "street": "streetwear"}
        s = prefs.get("style", "")
        if s in style_labels:
            sources.append(f"стиль: {style_labels[s]}")

    prefix = "💡 *Рекомендації для тебе:*"
    if sources:
        prefix += f"\n_({', '.join(sources)})_"

    await send_products_page(
        update.message, recs, user_id,
        page=0,
        prefix=prefix,
        context=context,
        list_key="recs_list",
    )


async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Дозволяє перенастроїти стильові вподобання."""
    await _start_onboarding(update.effective_user.id, update.message)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скидає всі дані рекомендаційної системи для тестування."""
    user_id = update.effective_user.id
    stats = reset_user_recommendations(user_id)

    lines = [
        "🔄 *Рекомендаційну систему скинуто:*\n",
        f"• Вподобання (онбординг): {stats['preferences']}",
        f"• Взаємодії (view/like/cart): {stats['interactions']} записів",
        f"• Інтенти запитів: {stats['query_intents']} записів",
        f"• Вибране: {stats['favorites']} записів",
        f"• Сесія (кошик, чат): {stats['session']}",
        "\nТепер бот сприймає тебе як нового користувача.",
        "Натисни /start щоб почати заново.",
    ]
    await safe_reply(update.message, "\n".join(lines))


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує що рекомендаційна система знає про користувача."""
    user_id = update.effective_user.id
    text = _build_profile_text(user_id)
    await safe_reply(update.message, text)


def _build_profile_text(user_id: int) -> str:
    """Формує текст профілю рекомендацій (використовується і в адмін-панелі)."""
    lines = ["📊 *Твій профіль рекомендацій*\n"]

    # 1. Анкета (explicit)
    prefs = get_user_preferences(user_id)
    if prefs.get("onboarding_done"):
        style_labels = {"sport": "🏃 Спортивний", "casual": "👕 Casual",
                        "classic": "👔 Класичний", "street": "🔥 Streetwear"}
        budget_labels = {"low": "до 2000 грн", "mid": "2000–5000 грн", "high": "5000+ грн"}
        color_labels = {"dark": "темні", "light": "світлі",
                        "bright": "яскраві", "any": "різні"}
        lines.append(
            f"🎨 *Анкета:* {style_labels.get(prefs.get('style'), '—')}, "
            f"бюджет {budget_labels.get(prefs.get('budget'), '—')}, "
            f"розмір {prefs.get('size', '—')}, "
            f"кольори: {color_labels.get(prefs.get('colors'), '—')}"
        )
    else:
        lines.append("🎨 *Анкета:* не пройдена (/style)")

    # 2. Запити (query)
    stats = get_query_intent_stats(user_id)
    if stats:
        parts = []
        cats = stats.get("categories", {})
        if cats:
            sorted_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
            cat_str = ", ".join(f"{c} ×{n}" for c, n in sorted_cats)
            parts.append(cat_str)
        avg = stats.get("avg_price")
        if avg:
            parts.append(f"середня ціна ~{avg:.0f} грн")
        cols = stats.get("colors", {})
        if cols:
            sorted_cols = sorted(cols.items(), key=lambda x: x[1], reverse=True)[:3]
            col_str = ", ".join(f"{c} ×{n}" for c, n in sorted_cols)
            parts.append(f"кольори: {col_str}")
        lines.append(f"🔍 *Запити:* {'; '.join(parts)}")
    else:
        lines.append("🔍 *Запити:* ще немає даних")

    # 3. Взаємодії (implicit)
    interactions = get_user_interactions(user_id)
    if interactions:
        action_counts = Counter(i["action"] for i in interactions)
        parts = []
        if action_counts.get("view"):
            parts.append(f"{action_counts['view']} переглядів")
        if action_counts.get("like"):
            parts.append(f"{action_counts['like']} лайків")
        if action_counts.get("cart"):
            parts.append(f"{action_counts['cart']} у кошик")
        lines.append(f"👁 *Взаємодії:* {', '.join(parts)}")
    else:
        lines.append("👁 *Взаємодії:* ще немає даних")

    # 4. Комбінований профіль
    profile = build_user_profile(user_id)
    if profile is not None:
        cat_scores = [(CATEGORIES[i], profile[i]) for i in range(len(CATEGORIES))]
        cat_scores = [(c, s) for c, s in cat_scores if s > 0.01]
        cat_scores.sort(key=lambda x: x[1], reverse=True)

        if cat_scores:
            top = cat_scores[:5]
            cat_lines = ", ".join(f"{c} ({s:.2f})" for c, s in top)
            lines.append(f"\n📈 *Топ-категорії:* {cat_lines}")

        offset = len(CATEGORIES)
        brand_scores = [(BRANDS[i], profile[offset + i]) for i in range(len(BRANDS))]
        brand_scores = [(b, s) for b, s in brand_scores if s > 0.01]
        brand_scores.sort(key=lambda x: x[1], reverse=True)

        if brand_scores:
            top_b = brand_scores[:4]
            brand_lines = ", ".join(f"{b} ({s:.2f})" for b, s in top_b)
            lines.append(f"🏷 *Топ-бренди:* {brand_lines}")

        sources = []
        if prefs.get("onboarding_done"):
            sources.append("анкета ×2.0")
        if stats:
            sources.append("запити ×1.5")
        if interactions:
            sources.append("взаємодії ×1.0")
        if sources:
            lines.append(f"\n⚖️ *Джерела профілю:* {', '.join(sources)}")
    else:
        lines.append("\n📈 *Профіль:* порожній — почни переглядати товари!")

    return "\n".join(lines)


# ── Онбординг ────────────────────────────────────────────────────────────────

async def _start_onboarding(user_id: int, target):
    """Запускає крок 1 онбординг-анкети."""
    keyboard = [
        [InlineKeyboardButton("🏃 Спортивний", callback_data="onb_style_sport")],
        [InlineKeyboardButton("👕 Casual", callback_data="onb_style_casual")],
        [InlineKeyboardButton("👔 Класичний", callback_data="onb_style_classic")],
        [InlineKeyboardButton("🔥 Streetwear", callback_data="onb_style_street")],
    ]
    text = "🎨 *Крок 1/4 — Який стиль тобі ближче?*"
    if hasattr(target, "reply_text"):
        await target.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await target.message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=InlineKeyboardMarkup(keyboard))


# ── Callbacks ────────────────────────────────────────────────────────────────

async def handle_callback(query, user_id: int, data: str,
                          context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обробляє callback онбордингу та рекомендацій. Повертає True якщо оброблено."""

    if data == "onb_start":
        await _start_onboarding(user_id, query)
        return True

    if data == "onb_skip":
        await query.message.edit_text("👌 Добре! Можеш пройти опитування пізніше: /style")
        return True

    if data.startswith("onb_style_"):
        style = data[10:]
        prefs = get_user_preferences(user_id)
        prefs["style"] = style
        save_user_preferences(user_id, prefs)

        keyboard = [
            [InlineKeyboardButton("💵 до 2000 грн", callback_data="onb_budget_low")],
            [InlineKeyboardButton("💰 2000–5000 грн", callback_data="onb_budget_mid")],
            [InlineKeyboardButton("💎 5000+ грн", callback_data="onb_budget_high")],
        ]
        await query.message.edit_text(
            "💰 *Крок 2/4 — Який бюджет на одну річ?*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True

    if data.startswith("onb_budget_"):
        budget = data[11:]
        prefs = get_user_preferences(user_id)
        prefs["budget"] = budget
        save_user_preferences(user_id, prefs)

        sizes = ["XS", "S", "M", "L", "XL", "XXL"]
        keyboard = [
            [InlineKeyboardButton(s, callback_data=f"onb_size_{s}") for s in sizes[:3]],
            [InlineKeyboardButton(s, callback_data=f"onb_size_{s}") for s in sizes[3:]],
        ]
        await query.message.edit_text(
            "📐 *Крок 3/4 — Який твій розмір одягу?*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True

    if data.startswith("onb_size_"):
        size = data[9:]
        prefs = get_user_preferences(user_id)
        prefs["size"] = size
        save_user_preferences(user_id, prefs)

        keyboard = [
            [InlineKeyboardButton("⬛ Темні (чорний, сірий)", callback_data="onb_color_dark")],
            [InlineKeyboardButton("⬜ Світлі (білий, бежевий)", callback_data="onb_color_light")],
            [InlineKeyboardButton("🔵 Яскраві (синій, червоний)", callback_data="onb_color_bright")],
            [InlineKeyboardButton("🌈 Різні / без переваг", callback_data="onb_color_any")],
        ]
        await query.message.edit_text(
            "🎨 *Крок 4/4 — Які кольори подобаються?*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True

    if data.startswith("onb_color_"):
        color_group = data[10:]
        prefs = get_user_preferences(user_id)
        prefs["colors"] = color_group
        prefs["onboarding_done"] = True
        save_user_preferences(user_id, prefs)

        style_labels = {"sport": "🏃 Спортивний", "casual": "👕 Casual",
                        "classic": "👔 Класичний", "street": "🔥 Streetwear"}
        budget_labels = {"low": "до 2000 грн", "mid": "2000–5000 грн", "high": "5000+ грн"}
        color_labels = {"dark": "⬛ Темні", "light": "⬜ Світлі",
                        "bright": "🔵 Яскраві", "any": "🌈 Різні"}

        await query.message.edit_text(
            f"✅ *Профіль стилю збережено!*\n\n"
            f"Стиль: {style_labels.get(prefs.get('style', ''), '—')}\n"
            f"Бюджет: {budget_labels.get(prefs.get('budget', ''), '—')}\n"
            f"Розмір: {prefs.get('size', '—')}\n"
            f"Кольори: {color_labels.get(color_group, '—')}\n\n"
            f"Тепер кнопка *💡 Для мене* покаже персоналізовані рекомендації!\n"
            f"Змінити вподобання: /style",
            parse_mode=ParseMode.MARKDOWN,
        )
        return True

    return False
