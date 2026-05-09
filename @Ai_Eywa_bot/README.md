# AI Chatbot для рекомендаційної системи інтернет-магазину

Telegram-бот з AI-асистентом на базі Google Gemini 2.5 Flash для інтернет-магазину одягу. Поєднує діалоговий інтерфейс з гібридною рекомендаційною системою на основі контентної фільтрації та косинусної подібності.

## Технології

- Python 3.11
- python-telegram-bot
- Google Gemini 2.5 Flash API
- NumPy, scikit-learn
- SQLite

## Встановлення

```bash
pip install -r requirements.txt
```

## Змінні середовища

Створи файл `.env`:

GEMINI_API_KEY=your_gemini_key
TELEGRAM_TOKEN=your_telegram_token
ADMIN_IDS=your_telegram_id
SHOP_NAME=your_shop_name
DB_PATH=shop.db
PAYMENT_DETAILS=your_payment_info

## Запуск

```bash
# Ініціалізація бази даних
python seed_data.py

# Запуск бота
python bot.py
```

## Тестування

```bash
pytest tests.py -v
```

## Скидання бази даних

```bash
del shop.db      # Windows
rm shop.db       # Linux/Mac
```

## Структура проекту

Бакалаврська робота — КНУБА, 2026  
Спеціальність 122 «Комп'ютерні науки»  
Автор: Поліщук Павло Богданович