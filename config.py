import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
KEY_PART_A = os.getenv("KEY_PART_A")

KEY_PART_B_PATH = Path.home() / ".message_tracker" / "key.part"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

if not KEY_PART_A:
    raise RuntimeError("KEY_PART_A не найден в .env")

if not KEY_PART_B_PATH.exists():
    raise RuntimeError(
        f"Вторая часть ключа не найдена: {KEY_PART_B_PATH}"
    )
