"""
recommender.py — гібридна рекомендаційна система (CBF)

Три джерела даних для побудови профілю користувача:
1. Explicit preferences — відповіді з онбординг-анкети (стиль, бюджет, розмір, кольори)
2. Query intent history — агрегація розпарсених пошукових запитів
3. Implicit interactions — перегляди, лайки, додавання в кошик

Алгоритм:
1. Кожен товар → числовий вектор ознак
2. Три профілі (explicit, query, implicit) → зважене об'єднання
3. Косинусна подібність між профілем і кожним товаром → ранжування
"""
import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from database import (
    get_all_products, get_user_interactions, get_product_by_id,
    get_user_preferences, get_query_intent_stats,
)

# ── Словники для one-hot кодування ────────────────────────────────────────────

CATEGORIES = [
    "куртки", "пальта", "худі", "светри", "футболки",
    "джинси", "штани", "сукні", "взуття", "аксесуари",
]

BRANDS = [
    "Nike", "Adidas", "Zara", "H&M", "Tommy Hilfiger",
    "New Balance", "Mango", "Pull&Bear",
    "The North Face", "Levi's", "Puma", "Vans",
    "Calvin Klein", "Timberland", "Under Armour",
]

MATERIALS = [
    "бавовна", "поліестер", "вовна", "шкіра",
    "денім", "льон", "синтетика", "акрил", "нейлон", "еластан",
]

COLORS = [
    "чорний", "білий", "сірий", "синій",
    "червоний", "бежевий", "коричневий",
    "жовтий", "зелений", "хакі", "рожевий", "блакитний",
]

PRICE_MIN = 300
PRICE_MAX = 10000

INTERACTION_WEIGHTS = {"view": 1, "like": 3, "cart": 5}

# Літерні розміри — для відділення від числових (взуття)
LETTER_SIZES = {"XS", "S", "M", "L", "XL", "XXL"}

# Маппінг стилів на категорії та бренди
STYLE_MAP = {
    "sport": {
        "categories": {"куртки": 0.5, "худі": 0.8, "футболки": 0.7,
                        "штани": 0.6, "взуття": 0.9},
        "brands": {"Nike": 1.0, "Adidas": 1.0, "New Balance": 0.9,
                   "Puma": 0.8, "The North Face": 0.7, "Under Armour": 0.9},
    },
    "casual": {
        "categories": {"худі": 0.7, "футболки": 0.8, "джинси": 0.9,
                        "светри": 0.6, "куртки": 0.5, "взуття": 0.5},
        "brands": {"Zara": 0.8, "H&M": 0.9, "Pull&Bear": 0.9,
                   "Mango": 0.7, "Levi's": 0.8, "Timberland": 0.5},
    },
    "classic": {
        "categories": {"пальта": 0.9, "светри": 0.7, "штани": 0.8,
                        "сукні": 0.6, "аксесуари": 0.5},
        "brands": {"Tommy Hilfiger": 1.0, "Zara": 0.6, "Mango": 0.7,
                   "Calvin Klein": 0.9},
    },
    "street": {
        "categories": {"худі": 1.0, "джинси": 0.8, "футболки": 0.7,
                        "куртки": 0.6, "взуття": 0.9, "аксесуари": 0.5},
        "brands": {"Nike": 0.8, "Adidas": 0.7, "New Balance": 0.8,
                   "Pull&Bear": 0.6, "Vans": 0.9, "Puma": 0.6,
                   "The North Face": 0.5, "Timberland": 0.6},
    },
}

BUDGET_MAP = {
    "low":  {"target": 1500, "range": 1000},
    "mid":  {"target": 3500, "range": 2000},
    "high": {"target": 6500, "range": 3000},
}

COLOR_GROUP_MAP = {
    "dark":   ["чорний", "сірий", "коричневий", "хакі"],
    "light":  ["білий", "бежевий"],
    "bright": ["синій", "червоний", "жовтий", "зелений", "рожевий", "блакитний"],
}

VECTOR_SIZE = len(CATEGORIES) + len(BRANDS) + len(MATERIALS) + len(COLORS) + 1


def product_to_vector(product: dict) -> np.ndarray:
    """Перетворює товар у числовий вектор ознак."""
    vector = []

    cat = product.get("category", "").lower().strip()
    vector += [1 if c == cat else 0 for c in CATEGORIES]

    brand = product.get("brand", "").strip()
    vector += [1 if b == brand else 0 for b in BRANDS]

    material = product.get("material", "").lower()
    vector += [1 if m in material else 0 for m in MATERIALS]

    try:
        raw = product.get("colors", "[]")
        colors_list = json.loads(raw) if isinstance(raw, str) else raw
        colors_lower = [c.lower() for c in colors_list]
    except Exception:
        colors_lower = []
    vector += [1 if c in colors_lower else 0 for c in COLORS]

    price = float(product.get("price", PRICE_MIN))
    normalized = (price - PRICE_MIN) / (PRICE_MAX - PRICE_MIN)
    vector.append(max(0.0, min(1.0, normalized)))

    return np.array(vector, dtype=float)


# ── Побудова профілю з трьох джерел ──────────────────────────────────────────

def _build_explicit_profile(user_id: int) -> np.ndarray | None:
    """Профіль з онбординг-анкети (explicit preferences)."""
    prefs = get_user_preferences(user_id)
    if not prefs or not prefs.get("onboarding_done"):
        return None

    vector = np.zeros(VECTOR_SIZE, dtype=float)

    # Стиль → категорії та бренди
    style = prefs.get("style")
    if style and style in STYLE_MAP:
        smap = STYLE_MAP[style]
        for cat, weight in smap.get("categories", {}).items():
            if cat in CATEGORIES:
                vector[CATEGORIES.index(cat)] = weight
        for brand, weight in smap.get("brands", {}).items():
            if brand in BRANDS:
                idx = len(CATEGORIES) + BRANDS.index(brand)
                vector[idx] = weight

    # Кольори
    color_group = prefs.get("colors")
    if color_group and color_group in COLOR_GROUP_MAP:
        offset = len(CATEGORIES) + len(BRANDS) + len(MATERIALS)
        for color in COLOR_GROUP_MAP[color_group]:
            if color in COLORS:
                vector[offset + COLORS.index(color)] = 0.8
    elif color_group == "any":
        offset = len(CATEGORIES) + len(BRANDS) + len(MATERIALS)
        for i in range(len(COLORS)):
            vector[offset + i] = 0.3

    # Бюджет → нормалізована ціна
    budget = prefs.get("budget")
    if budget and budget in BUDGET_MAP:
        target = BUDGET_MAP[budget]["target"]
        normalized = (target - PRICE_MIN) / (PRICE_MAX - PRICE_MIN)
        vector[-1] = max(0.0, min(1.0, normalized))

    return vector


def _build_query_profile(user_id: int) -> np.ndarray | None:
    """Профіль з агрегованих пошукових запитів."""
    stats = get_query_intent_stats(user_id)
    if not stats:
        return None

    vector = np.zeros(VECTOR_SIZE, dtype=float)

    cats = stats.get("categories", {})
    if cats:
        max_count = max(cats.values())
        for cat, count in cats.items():
            if cat in CATEGORIES:
                vector[CATEGORIES.index(cat)] = count / max_count

    cols = stats.get("colors", {})
    if cols:
        max_count = max(cols.values())
        offset = len(CATEGORIES) + len(BRANDS) + len(MATERIALS)
        for color, count in cols.items():
            if color in COLORS:
                vector[offset + COLORS.index(color)] = count / max_count

    avg_price = stats.get("avg_price")
    if avg_price:
        normalized = (avg_price - PRICE_MIN) / (PRICE_MAX - PRICE_MIN)
        vector[-1] = max(0.0, min(1.0, normalized))

    return vector


def _build_interaction_profile(user_id: int) -> np.ndarray | None:
    """Профіль з неявних взаємодій (перегляди, лайки, кошик)."""
    interactions = get_user_interactions(user_id)
    if not interactions:
        return None

    weighted_vectors = []
    for interaction in interactions:
        product = get_product_by_id(interaction["product_id"])
        if product:
            weight = INTERACTION_WEIGHTS.get(interaction["action"], 1)
            weighted_vectors.append(product_to_vector(product) * weight)

    if not weighted_vectors:
        return None

    return np.mean(weighted_vectors, axis=0)


def build_user_profile(user_id: int) -> np.ndarray | None:
    """
    Об'єднує три профілі з вагами:
    - explicit (онбординг):  вага 2.0
    - query (запити):        вага 1.5
    - implicit (взаємодії):  вага 1.0
    """
    explicit = _build_explicit_profile(user_id)
    query = _build_query_profile(user_id)
    implicit = _build_interaction_profile(user_id)

    profiles = []
    if explicit is not None:
        profiles.append(explicit * 2.0)
    if query is not None:
        profiles.append(query * 1.5)
    if implicit is not None:
        profiles.append(implicit * 1.0)

    if not profiles:
        return None

    total_weight = sum([2.0] * (explicit is not None) +
                       [1.5] * (query is not None) +
                       [1.0] * (implicit is not None))
    combined = sum(profiles) / total_weight

    return combined


# ── Головні функції ──────────────────────────────────────────────────────────

def get_recommendations(user_id: int, top_n: int = 5,
                        candidate_products: list | None = None) -> list:
    """Повертає топ-N рекомендованих товарів для користувача."""
    products = candidate_products if candidate_products is not None else get_all_products()
    if not products:
        return []

    user_profile = build_user_profile(user_id)
    if user_profile is None:
        return products[:top_n]

    product_vectors = np.array([product_to_vector(p) for p in products])
    profile_2d = user_profile.reshape(1, -1)
    similarities = cosine_similarity(profile_2d, product_vectors)[0]
    ranked_indices = np.argsort(similarities)[::-1]

    # Фільтр по розміру з вподобань (якщо є)
    prefs = get_user_preferences(user_id)
    preferred_size = prefs.get("size")

    results = []
    for i in ranked_indices:
        p = products[i]
        if preferred_size and preferred_size in LETTER_SIZES:
            # Літерний розмір з анкети — не застосовуємо до взуття
            # (числові розміри) та аксесуарів (One Size)
            cat = p.get("category", "").lower().strip()
            if cat in ("взуття", "аксесуари"):
                results.append(p)
            else:
                try:
                    sizes = json.loads(p["sizes"]) if isinstance(p["sizes"], str) else p["sizes"]
                except Exception:
                    sizes = []
                if preferred_size in sizes:
                    results.append(p)
        else:
            results.append(p)
        if len(results) >= top_n:
            break

    # Фолбек: якщо з фільтром розміру набралось мало
    if preferred_size and len(results) < top_n:
        seen_ids = {p["id"] for p in results}
        for i in ranked_indices:
            if products[i]["id"] not in seen_ids:
                results.append(products[i])
            if len(results) >= top_n:
                break

    return results


def score_products(products: list, user_id: int) -> list:
    """Ранжує переданий список товарів за релевантністю для користувача."""
    return get_recommendations(user_id, top_n=len(products),
                               candidate_products=products)
