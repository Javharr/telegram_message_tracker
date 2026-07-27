import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MASTER_KEK = os.getenv("MASTER_KEK")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

if not MASTER_KEK:
    raise RuntimeError("MASTER_KEK не найден в .env")
