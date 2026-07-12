
import os


BOT_TOKEN = os.getenv("8934712261:AAGn3tmmtJw6ScfDvhcGtY4C_v-u4DroDoM")

if not BOT_TOKEN:
    raise RuntimeError("Переменная BOT_TOKEN не установлена")