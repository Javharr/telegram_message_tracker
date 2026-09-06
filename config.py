import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

if not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY не найден. Добавь его в Railway Variables!")