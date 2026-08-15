"""
config.py — конфігурація бота Nazerva
Всі секрети читаються з .env файлу.
"""
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

DB_PATH = os.getenv("DB_PATH", "shop.db")
SHOP_NAME = os.getenv("SHOP_NAME", "Nazerva")

# Telegram ID адміністраторів (через кому в .env)
_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit()]

# ID чату/групи для повідомлень про нові замовлення
_orders_chat_id = os.getenv("ORDERS_CHAT_ID", "").strip()
ORDERS_CHAT_ID = int(_orders_chat_id) if _orders_chat_id else None

# Реквізити для оплати (показуються користувачу при оформленні)
PAYMENT_DETAILS = os.getenv(
    "PAYMENT_DETAILS",
    "Payment details are not configured.",
)
