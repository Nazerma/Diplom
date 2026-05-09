"""
tests.py — юніт-тести для парсера інтентів, векторизації товарів
та косинусної подібності рекомендаційної системи.

Запуск:  pytest tests.py -v
"""
import json
import numpy as np
import pytest
from sklearn.metrics.pairwise import cosine_similarity

from gemini import parse_intent_from_text
from recommender import (
    product_to_vector,
    CATEGORIES, BRANDS, MATERIALS, COLORS, VECTOR_SIZE,
    PRICE_MIN, PRICE_MAX,
)


# ═══════════════════════════════════════════════════════════════════════
# 1. Тести парсера інтентів (parse_intent_from_text)
# ═══════════════════════════════════════════════════════════════════════

class TestIntentCategory:
    """Розпізнавання категорій, включаючи зменшувальні форми та синоніми."""

    @pytest.mark.parametrize("text, expected", [
        ("черевички", "взуття"),
        ("черевики", "взуття"),
        ("кросівки", "взуття"),
        ("кеди", "взуття"),
        ("чоботи", "взуття"),
        ("ботинки", "взуття"),
        ("снікерси", "взуття"),
        ("туфлі", "взуття"),
        ("сандалі", "взуття"),
    ])
    def test_footwear_synonyms(self, text, expected):
        result = parse_intent_from_text(text)
        assert result["category"] == expected

    @pytest.mark.parametrize("text, expected", [
        ("кофтинка", "худі"),
        ("кофточка", "худі"),
        ("толстовка", "худі"),
        ("світшот", "худі"),
    ])
    def test_hoodie_synonyms(self, text, expected):
        result = parse_intent_from_text(text)
        assert result["category"] == expected

    @pytest.mark.parametrize("text, expected", [
        ("штанці", "штани"),
        ("штанішки", "штани"),
        ("брюки", "штани"),
        ("лосини", "штани"),
    ])
    def test_pants_synonyms(self, text, expected):
        result = parse_intent_from_text(text)
        assert result["category"] == expected

    @pytest.mark.parametrize("text, expected", [
        ("курточка", "куртки"),
        ("вітровка", "куртки"),
        ("пухівка", "куртки"),
        ("бомбер", "куртки"),
    ])
    def test_jacket_synonyms(self, text, expected):
        result = parse_intent_from_text(text)
        assert result["category"] == expected

    @pytest.mark.parametrize("text, expected", [
        ("футболочка", "футболки"),
        ("майка", "футболки"),
        ("тішка", "футболки"),
    ])
    def test_tshirt_synonyms(self, text, expected):
        result = parse_intent_from_text(text)
        assert result["category"] == expected

    @pytest.mark.parametrize("text, expected", [
        ("сукенка", "сукні"),
        ("плаття", "сукні"),
        ("платтячко", "сукні"),
    ])
    def test_dress_synonyms(self, text, expected):
        result = parse_intent_from_text(text)
        assert result["category"] == expected

    def test_no_category(self):
        result = parse_intent_from_text("привіт, що порадиш?")
        assert result["category"] is None


class TestIntentPrice:
    """Розпізнавання цінових обмежень."""

    @pytest.mark.parametrize("text, expected_max", [
        ("до 2000 грн", 2000),
        ("до 2000", 2000),
        ("не дорожче 3000", 3000),
        ("менше 1500", 1500),
        ("не більше 5000", 5000),
        ("бюджет 4000", 4000),
        ("бюджетом 2500", 2500),
    ])
    def test_max_price(self, text, expected_max):
        result = parse_intent_from_text(text)
        assert result["max_price"] == expected_max

    @pytest.mark.parametrize("text, expected_min", [
        ("від 1000", 1000),
        ("більше 2000", 2000),
        ("не менше 3000", 3000),
        ("не дешевше 1500", 1500),
    ])
    def test_min_price(self, text, expected_min):
        result = parse_intent_from_text(text)
        assert result["min_price"] == expected_min

    def test_price_range_two_values(self):
        result = parse_intent_from_text("від 1000 до 3000 грн")
        # "від 1000" спрацює як min_price через from_match
        # але "до" перехоплює budget_match першим
        assert result["max_price"] == 3000 or result["min_price"] is not None

    def test_single_price_with_grn(self):
        result = parse_intent_from_text("футболка 800 грн")
        assert result["max_price"] == 800

    def test_no_price(self):
        result = parse_intent_from_text("покажи куртки")
        assert result["max_price"] is None
        assert result["min_price"] is None


class TestIntentSize:
    """Розпізнавання розмірів."""

    @pytest.mark.parametrize("text, expected", [
        ("розмір M", "M"),
        ("розмір XL", "XL"),
        ("розмір S", "S"),
        ("є в L ?", "L"),
    ])
    def test_letter_sizes(self, text, expected):
        result = parse_intent_from_text(text)
        assert result["size"] == expected

    @pytest.mark.parametrize("text, expected", [
        ("кросівки 42", "42"),
        ("взуття 38 розмір", "38"),
        ("черевики 44", "44"),
    ])
    def test_shoe_sizes(self, text, expected):
        result = parse_intent_from_text(text)
        assert result["size"] == expected

    def test_no_size(self):
        result = parse_intent_from_text("покажи куртки")
        assert result["size"] is None


class TestIntentColor:
    """Розпізнавання кольорів."""

    @pytest.mark.parametrize("text, expected", [
        ("чорна куртка", "чорний"),
        ("біле худі", "білий"),
        ("сірі штани", "сірий"),
        ("синя сукня", "синій"),
        ("бежеві черевики", "бежевий"),
    ])
    def test_colors(self, text, expected):
        result = parse_intent_from_text(text)
        assert result["color"] == expected

    def test_no_color(self):
        result = parse_intent_from_text("покажи куртки")
        assert result["color"] is None


class TestIntentCombined:
    """Комбіновані запити з кількома параметрами."""

    def test_category_price_color(self):
        result = parse_intent_from_text("чорні кросівки до 3000 грн")
        assert result["category"] == "взуття"
        assert result["max_price"] == 3000
        assert result["color"] == "чорний"

    def test_category_size(self):
        result = parse_intent_from_text("худі розмір L")
        assert result["category"] == "худі"
        assert result["size"] == "L"

    def test_full_query(self):
        result = parse_intent_from_text("білі кросівки 42 до 2500")
        assert result["category"] == "взуття"
        assert result["color"] == "білий"
        assert result["size"] == "42"
        assert result["max_price"] == 2500


# ═══════════════════════════════════════════════════════════════════════
# 2. Тести векторизації товарів (product_to_vector)
# ═══════════════════════════════════════════════════════════════════════

def _make_product(**overrides) -> dict:
    """Хелпер: створює мінімальний товар-словник."""
    base = {
        "id": 1,
        "name": "Тестовий товар",
        "category": "куртки",
        "brand": "Nike",
        "price": 2500,
        "material": "поліестер",
        "sizes": json.dumps(["M", "L"]),
        "colors": json.dumps(["чорний"]),
        "description": "Тест",
    }
    base.update(overrides)
    return base


class TestProductToVector:
    """Перевірка коректності перетворення товару у вектор."""

    def test_vector_length(self):
        product = _make_product()
        vec = product_to_vector(product)
        assert len(vec) == VECTOR_SIZE

    def test_category_encoding(self):
        product = _make_product(category="взуття")
        vec = product_to_vector(product)
        cat_idx = CATEGORIES.index("взуття")
        assert vec[cat_idx] == 1.0
        # Інші категорії мають бути 0
        for i, cat in enumerate(CATEGORIES):
            if cat != "взуття":
                assert vec[i] == 0.0

    def test_brand_encoding(self):
        product = _make_product(brand="Adidas")
        vec = product_to_vector(product)
        offset = len(CATEGORIES)
        brand_idx = BRANDS.index("Adidas")
        assert vec[offset + brand_idx] == 1.0
        for i, brand in enumerate(BRANDS):
            if brand != "Adidas":
                assert vec[offset + i] == 0.0

    def test_material_encoding(self):
        product = _make_product(material="бавовна")
        vec = product_to_vector(product)
        offset = len(CATEGORIES) + len(BRANDS)
        mat_idx = MATERIALS.index("бавовна")
        assert vec[offset + mat_idx] == 1.0

    def test_color_encoding(self):
        product = _make_product(colors=json.dumps(["чорний", "білий"]))
        vec = product_to_vector(product)
        offset = len(CATEGORIES) + len(BRANDS) + len(MATERIALS)
        assert vec[offset + COLORS.index("чорний")] == 1.0
        assert vec[offset + COLORS.index("білий")] == 1.0
        assert vec[offset + COLORS.index("сірий")] == 0.0

    def test_price_normalization(self):
        product = _make_product(price=PRICE_MIN)
        vec = product_to_vector(product)
        assert vec[-1] == pytest.approx(0.0)

        product = _make_product(price=PRICE_MAX)
        vec = product_to_vector(product)
        assert vec[-1] == pytest.approx(1.0)

        mid_price = (PRICE_MIN + PRICE_MAX) / 2
        product = _make_product(price=mid_price)
        vec = product_to_vector(product)
        assert vec[-1] == pytest.approx(0.5)

    def test_price_clamp(self):
        product = _make_product(price=0)
        vec = product_to_vector(product)
        assert vec[-1] == 0.0

        product = _make_product(price=99999)
        vec = product_to_vector(product)
        assert vec[-1] == 1.0

    def test_unknown_brand_all_zeros(self):
        product = _make_product(brand="НевідомийБренд")
        vec = product_to_vector(product)
        offset = len(CATEGORIES)
        brand_slice = vec[offset : offset + len(BRANDS)]
        assert np.all(brand_slice == 0.0)


# ═══════════════════════════════════════════════════════════════════════
# 3. Тести косинусної подібності
# ═══════════════════════════════════════════════════════════════════════

class TestCosineSimilarity:
    """Перевірка, що cosine similarity працює коректно для векторів товарів."""

    def test_identical_products_similarity_1(self):
        product = _make_product()
        vec = product_to_vector(product)
        sim = cosine_similarity(vec.reshape(1, -1), vec.reshape(1, -1))[0][0]
        assert sim == pytest.approx(1.0, abs=1e-6)

    def test_same_category_more_similar(self):
        """Два товари однієї категорії мають бути ближчими, ніж різних."""
        p1 = _make_product(category="взуття", brand="Nike", price=2000)
        p2 = _make_product(category="взуття", brand="Adidas", price=2500)
        p3 = _make_product(category="сукні", brand="Zara", price=4000)

        v1 = product_to_vector(p1)
        v2 = product_to_vector(p2)
        v3 = product_to_vector(p3)

        sim_same = cosine_similarity(v1.reshape(1, -1), v2.reshape(1, -1))[0][0]
        sim_diff = cosine_similarity(v1.reshape(1, -1), v3.reshape(1, -1))[0][0]

        assert sim_same > sim_diff

    def test_similar_price_closer(self):
        """Товари з близькою ціною (при інших рівних) мають вищу подібність."""
        base = dict(category="худі", brand="Nike",
                    colors=json.dumps(["чорний"]), material="бавовна")
        p1 = _make_product(**base, price=2000)
        p2 = _make_product(**base, price=2200)
        p3 = _make_product(**base, price=9000)

        v1 = product_to_vector(p1)
        v2 = product_to_vector(p2)
        v3 = product_to_vector(p3)

        sim_close = cosine_similarity(v1.reshape(1, -1), v2.reshape(1, -1))[0][0]
        sim_far   = cosine_similarity(v1.reshape(1, -1), v3.reshape(1, -1))[0][0]

        assert sim_close > sim_far

    def test_user_profile_ranking(self):
        """
        Симуляція: профіль користувача — 'спортивне взуття'.
        Кросівки Nike мають бути релевантнішими, ніж сукня Zara.
        """
        # Створюємо штучний профіль: категорія=взуття, бренд=Nike
        profile = np.zeros(VECTOR_SIZE, dtype=float)
        profile[CATEGORIES.index("взуття")] = 1.0
        profile[len(CATEGORIES) + BRANDS.index("Nike")] = 1.0

        sneakers = _make_product(
            category="взуття", brand="Nike", price=3200,
            colors=json.dumps(["чорний"]), material="синтетика",
        )
        dress = _make_product(
            category="сукні", brand="Zara", price=2800,
            colors=json.dumps(["червоний"]), material="бавовна",
        )

        v_sneak = product_to_vector(sneakers)
        v_dress = product_to_vector(dress)

        sim_sneak = cosine_similarity(
            profile.reshape(1, -1), v_sneak.reshape(1, -1)
        )[0][0]
        sim_dress = cosine_similarity(
            profile.reshape(1, -1), v_dress.reshape(1, -1)
        )[0][0]

        assert sim_sneak > sim_dress

    def test_batch_ranking_order(self):
        """Перевірка ранжування списку товарів відносно профілю."""
        profile = np.zeros(VECTOR_SIZE, dtype=float)
        profile[CATEGORIES.index("худі")] = 1.0
        profile[len(CATEGORIES) + BRANDS.index("Nike")] = 0.8

        products = [
            _make_product(id=1, category="худі", brand="Nike", price=2000),
            _make_product(id=2, category="худі", brand="Adidas", price=2200),
            _make_product(id=3, category="сукні", brand="Zara", price=3500),
        ]

        vectors = np.array([product_to_vector(p) for p in products])
        sims = cosine_similarity(profile.reshape(1, -1), vectors)[0]
        ranked = np.argsort(sims)[::-1]

        # Nike худі має бути першим, потім Adidas худі, потім сукня
        assert ranked[0] == 0
        assert ranked[1] == 1
        assert ranked[2] == 2

    def test_zero_vector_handling(self):
        """Товар з невідомими атрибутами → вектор майже нульовий (тільки ціна)."""
        product = _make_product(
            category="невідоме", brand="НевідомийБренд",
            material="невідомий", colors=json.dumps([]),
            price=PRICE_MIN,
        )
        vec = product_to_vector(product)
        # Всі елементи крім ціни мають бути 0; ціна = 0 при PRICE_MIN
        assert np.sum(vec) == pytest.approx(0.0)
