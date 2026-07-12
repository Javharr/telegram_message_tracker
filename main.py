import asyncio
import logging
import shutil
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    BusinessConnection,
    BusinessMessagesDeleted,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import BOT_TOKEN
from database import (
    create_tables,
    delete_user_messages,
    get_connection_owner_chat_id,
    get_connection_owner_user_id,
    get_message,
    get_user_connection,
    get_user_statistics,
    mark_message_deleted,
    save_business_connection,
    save_message,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BASE_DIR = Path(__file__).resolve().parent
MEDIA_DIR = BASE_DIR / "media"


def current_time() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def formatted_time() -> str:
    return datetime.now().strftime(
        "%d.%m.%Y в %H:%M"
    )


def sanitize_path_part(
    value: str | int,
) -> str:
    return "".join(
        character
        if character.isalnum()
        or character in ("-", "_")
        else "_"
        for character in str(value)
    )


def get_sender_id(
    message: Message,
) -> int | None:
    if message.from_user:
        return message.from_user.id

    if message.sender_chat:
        return message.sender_chat.id

    return None


def get_sender_name(
    message: Message,
) -> str:
    if message.from_user:
        return message.from_user.full_name

    if message.sender_chat:
        return message.sender_chat.title

    return "Неизвестный отправитель"


def get_message_text(
    message: Message,
) -> str:
    if message.text:
        return message.text

    if message.caption:
        return message.caption

    if message.photo:
        return "[Фотография]"

    if message.video:
        return "[Видео]"

    if message.video_note:
        return "[Видеосообщение]"

    if message.voice:
        return "[Голосовое сообщение]"

    if message.audio:
        return "[Аудиозапись]"

    if message.animation:
        return "[GIF-анимация]"

    if message.document:
        filename = (
            message.document.file_name
            or "без названия"
        )

        return f"[Документ: {filename}]"

    if message.sticker:
        emoji = message.sticker.emoji or ""

        return f"[Стикер {emoji}]"

    if message.contact:
        return "[Контакт]"

    if message.location:
        return "[Геолокация]"

    return "[Сообщение без текста]"


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Как подключить",
                    callback_data="instructions",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="statistics",
                ),
                InlineKeyboardButton(
                    text="🟢 Статус",
                    callback_data="status",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧰 Возможности",
                    callback_data="features",
                ),
                InlineKeyboardButton(
                    text="ℹ️ О боте",
                    callback_data="about",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить мои данные",
                    callback_data="delete_data",
                ),
            ],
        ]
    )


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data="main_menu",
                ),
            ],
        ]
    )


def get_delete_confirmation_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=(
                        "confirm_delete_data"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="main_menu",
                ),
            ],
        ]
    )


def get_main_menu_text() -> str:
    return (
        "🛡 <b>MESSAGE TRACKER</b>\n\n"
        "Сохраняю входящие сообщения и медиа "
        "до того, как собеседник изменит "
        "или удалит их.\n\n"
        "🔹 Удалённые сообщения\n"
        "🔹 История редактирования\n"
        "🔹 Фото, видео и документы\n"
        "🔹 Голосовые и видеосообщения\n"
        "🔹 Одноразовые медиа через ответ\n\n"
        "🟢 <b>Система работает</b>\n\n"
        "Выбери нужный раздел:"
    )


def get_instructions_text() -> str:
    return (
        "📖 <b>КАК ПОДКЛЮЧИТЬ БОТА</b>\n\n"
        "1️⃣ Открой настройки Telegram.\n\n"
        "2️⃣ Перейди в раздел "
        "<b>Автоматизация чатов</b>.\n\n"
        "3️⃣ Нажми «Добавить бота».\n\n"
        "4️⃣ Выбери этого бота.\n\n"
        "5️⃣ Разреши доступ к нужным "
        "личным чатам.\n\n"
        "6️⃣ Сохрани настройки.\n\n"
        "После подключения бот автоматически "
        "начнёт сохранять входящие сообщения.\n\n"
        "🔥 <b>Одноразовое фото</b>\n"
        "Чтобы получить его копию, ответь "
        "на него обычным текстовым сообщением."
    )


def get_features_text() -> str:
    return (
        "🧰 <b>ВОЗМОЖНОСТИ</b>\n\n"
        "🗑 <b>Удалённые сообщения</b>\n"
        "Показывает текст, который удалил "
        "собеседник.\n\n"
        "✏️ <b>Редактирование</b>\n"
        "Показывает первоначальный и новый текст.\n\n"
        "🖼 <b>Фотографии</b>\n"
        "Сохраняет обычные входящие фотографии.\n\n"
        "🎬 <b>Видео и кружки</b>\n"
        "Сохраняет видео и видеосообщения.\n\n"
        "🎙 <b>Голосовые</b>\n"
        "Сохраняет входящие голосовые сообщения.\n\n"
        "📎 <b>Документы и GIF</b>\n"
        "Поддерживает файлы, аудио, "
        "GIF и стикеры.\n\n"
        "🔥 <b>Одноразовые медиа</b>\n"
        "Получает медиа, когда пользователь "
        "отвечает на исходное сообщение."
    )


def get_about_text() -> str:
    return (
        "ℹ️ <b>О MESSAGE TRACKER</b>\n\n"
        "Message Tracker сохраняет входящие "
        "сообщения и медиа из подключённых "
        "личных чатов.\n\n"
        "Бот работает через Telegram "
        "Chat Automation.\n\n"
        "🔐 Исходящие сообщения владельца "
        "не сохраняются.\n\n"
        "💾 Данные сохраняются на устройстве "
        "или сервере, где запущен бот.\n\n"
        "⚠️ Бот получает сообщения только "
        "из чатов, к которым пользователь "
        "предоставил доступ."
    )


def get_status_text(
    user_chat_id: int,
) -> str:
    connection = get_user_connection(
        user_chat_id
    )

    if connection is None:
        return (
            "🔴 <b>СТАТУС ПОДКЛЮЧЕНИЯ</b>\n\n"
            "Бот пока не подключён "
            "к автоматизации чатов.\n\n"
            "Открой раздел «Как подключить» "
            "и выполни инструкцию."
        )

    if connection["is_enabled"]:
        return (
            "🟢 <b>СТАТУС ПОДКЛЮЧЕНИЯ</b>\n\n"
            "✅ Автоматизация подключена\n"
            "✅ Получение сообщений активно\n"
            "✅ Сохранение медиа активно\n"
            "✅ Уведомления активны\n\n"
            f"👤 <b>Аккаунт:</b> "
            f"{escape(str(connection['full_name']))}"
        )

    return (
        "🟠 <b>СТАТУС ПОДКЛЮЧЕНИЯ</b>\n\n"
        "Автоматизация была отключена.\n\n"
        "Повторно добавь бота "
        "в настройках Telegram."
    )


def get_statistics_text(
    user_chat_id: int,
) -> str:
    statistics = get_user_statistics(
        user_chat_id
    )

    return (
        "📊 <b>СТАТИСТИКА</b>\n\n"
        f"💬 <b>Сохранено сообщений:</b> "
        f"{statistics['total_messages']}\n\n"
        f"🗑 <b>Зафиксировано удалений:</b> "
        f"{statistics['deleted_messages']}\n\n"
        f"🖼 <b>Сохранено медиа:</b> "
        f"{statistics['media_messages']}\n\n"
        f"👥 <b>Обработано чатов:</b> "
        f"{statistics['unique_chats']}"
    )


def get_media_data(
    source: Any,
) -> tuple[Any | None, str | None, str | None]:
    photo = getattr(
        source,
        "photo",
        None,
    )

    if photo:
        return photo[-1], "photo", ".jpg"

    video = getattr(
        source,
        "video",
        None,
    )

    if video:
        return video, "video", ".mp4"

    video_note = getattr(
        source,
        "video_note",
        None,
    )

    if video_note:
        return (
            video_note,
            "video_note",
            ".mp4",
        )

    voice = getattr(
        source,
        "voice",
        None,
    )

    if voice:
        return voice, "voice", ".ogg"

    audio = getattr(
        source,
        "audio",
        None,
    )

    if audio:
        filename = (
            getattr(
                audio,
                "file_name",
                None,
            )
            or "audio.mp3"
        )

        suffix = (
            Path(filename).suffix
            or ".mp3"
        )

        return audio, "audio", suffix

    animation = getattr(
        source,
        "animation",
        None,
    )

    if animation:
        filename = (
            getattr(
                animation,
                "file_name",
                None,
            )
            or "animation.mp4"
        )

        suffix = (
            Path(filename).suffix
            or ".mp4"
        )

        return (
            animation,
            "animation",
            suffix,
        )

    document = getattr(
        source,
        "document",
        None,
    )

    if document:
        filename = (
            getattr(
                document,
                "file_name",
                None,
            )
            or "document.bin"
        )

        suffix = (
            Path(filename).suffix
            or ".bin"
        )

        return (
            document,
            "document",
            suffix,
        )

    sticker = getattr(
        source,
        "sticker",
        None,
    )

    if sticker:
        if getattr(
            sticker,
            "is_animated",
            False,
        ):
            suffix = ".tgs"

        elif getattr(
            sticker,
            "is_video",
            False,
        ):
            suffix = ".webm"

        else:
            suffix = ".webp"

        return (
            sticker,
            "sticker",
            suffix,
        )

    return None, None, None


def build_media_path(
    connection_id: str,
    chat_id: int,
    filename: str,
) -> Path:
    folder = (
        MEDIA_DIR
        / sanitize_path_part(connection_id)
        / sanitize_path_part(chat_id)
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    return folder / filename


async def download_media_object(
    media_object: Any,
    destination_path: Path,
) -> str | None:
    if destination_path.exists():
        return str(destination_path)

    try:
        await bot.download(
            file=media_object,
            destination=destination_path,
            timeout=120,
        )

        return str(destination_path)

    except Exception:
        logging.exception(
            "Не удалось скачать медиа в %s",
            destination_path,
        )

        return None


async def download_source_media(
    source: Any,
    connection_id: str,
    chat_id: int,
    filename_id: int,
    prefix: str = "",
) -> tuple[str | None, str | None]:
    media_object, media_type, suffix = (
        get_media_data(source)
    )

    if (
        media_object is None
        or media_type is None
        or suffix is None
    ):
        return None, None

    destination_path = build_media_path(
        connection_id=connection_id,
        chat_id=chat_id,
        filename=(
            f"{prefix}"
            f"{filename_id}_"
            f"{media_type}"
            f"{suffix}"
        ),
    )

    media_path = await download_media_object(
        media_object=media_object,
        destination_path=destination_path,
    )

    return media_type, media_path


async def send_media_file(
    chat_id: int,
    media_type: str,
    media_path: str,
    caption: str,
) -> None:
    path = Path(media_path)

    if not path.exists():
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ <b>Файл не найден</b>\n\n"
                "Запись о медиа существует, "
                "но сам файл отсутствует."
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    media_file = FSInputFile(path)

    try:
        if media_type == "photo":
            await bot.send_photo(
                chat_id=chat_id,
                photo=media_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        elif media_type == "video":
            await bot.send_video(
                chat_id=chat_id,
                video=media_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        elif media_type == "video_note":
            await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode=ParseMode.HTML,
            )

            await bot.send_video_note(
                chat_id=chat_id,
                video_note=media_file,
            )

        elif media_type == "voice":
            await bot.send_voice(
                chat_id=chat_id,
                voice=media_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        elif media_type == "audio":
            await bot.send_audio(
                chat_id=chat_id,
                audio=media_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        elif media_type == "animation":
            await bot.send_animation(
                chat_id=chat_id,
                animation=media_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        elif media_type == "sticker":
            await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode=ParseMode.HTML,
            )

            await bot.send_sticker(
                chat_id=chat_id,
                sticker=media_file,
            )

        else:
            await bot.send_document(
                chat_id=chat_id,
                document=media_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

    except Exception:
        logging.exception(
            "Не удалось отправить медиа %s",
            media_path,
        )


async def try_extract_media_from_owner_reply(
    message: Message,
    connection_id: str,
    owner_chat_id: int,
) -> bool:
    reply = message.reply_to_message

    if reply is not None:
        reply_message_id = getattr(
            reply,
            "message_id",
            message.message_id,
        )

        media_type, media_path = (
            await download_source_media(
                source=reply,
                connection_id=connection_id,
                chat_id=message.chat.id,
                filename_id=reply_message_id,
                prefix="reply_",
            )
        )

        if media_type and media_path:
            await send_media_file(
                chat_id=owner_chat_id,
                media_type=media_type,
                media_path=media_path,
                caption=(
                    "🔥 <b>ОДНОРАЗОВОЕ МЕДИА</b>\n\n"
                    "Медиа получено из сообщения, "
                    "на которое ты ответил.\n\n"
                    f"🕒 <b>Получено:</b> "
                    f"{formatted_time()}"
                ),
            )

            return True

    external = message.external_reply

    if external is not None:
        media_type, media_path = (
            await download_source_media(
                source=external,
                connection_id=connection_id,
                chat_id=message.chat.id,
                filename_id=message.message_id,
                prefix="external_reply_",
            )
        )

        if media_type and media_path:
            await send_media_file(
                chat_id=owner_chat_id,
                media_type=media_type,
                media_path=media_path,
                caption=(
                    "🔥 <b>ОДНОРАЗОВОЕ МЕДИА</b>\n\n"
                    "Медиа получено из сообщения, "
                    "на которое ты ответил.\n\n"
                    f"🕒 <b>Получено:</b> "
                    f"{formatted_time()}"
                ),
            )

            return True

    return False


async def send_saved_deleted_media(
    owner_chat_id: int,
    saved_message: dict[str, Any],
) -> None:
    media_type = saved_message.get(
        "media_type"
    )

    media_path = saved_message.get(
        "media_path"
    )

    if not media_type or not media_path:
        return

    sender_name = escape(
        str(
            saved_message.get(
                "sender_name"
            )
            or "Неизвестный"
        )
    )

    await send_media_file(
        chat_id=owner_chat_id,
        media_type=str(media_type),
        media_path=str(media_path),
        caption=(
            "🗑 <b>УДАЛЁННОЕ МЕДИА</b>\n\n"
            f"👤 <b>Отправитель:</b> "
            f"{sender_name}\n\n"
            f"🕒 <b>Удалено:</b> "
            f"{formatted_time()}"
        ),
    )


def delete_user_media(
    connection_ids: list[str],
) -> None:
    for connection_id in connection_ids:
        folder = (
            MEDIA_DIR
            / sanitize_path_part(
                connection_id
            )
        )

        if folder.exists():
            shutil.rmtree(folder)


@dp.message(CommandStart())
async def handle_start(
    message: Message,
) -> None:
    await message.answer(
        text=get_main_menu_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(),
    )


@dp.message(Command("help"))
async def handle_help_command(
    message: Message,
) -> None:
    await message.answer(
        text=get_instructions_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard(),
    )


@dp.message(Command("features"))
async def handle_features_command(
    message: Message,
) -> None:
    await message.answer(
        text=get_features_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard(),
    )


@dp.message(Command("status"))
async def handle_status_command(
    message: Message,
) -> None:
    await message.answer(
        text=get_status_text(
            message.from_user.id
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard(),
    )


@dp.message(Command("statistics"))
async def handle_statistics_command(
    message: Message,
) -> None:
    await message.answer(
        text=get_statistics_text(
            message.from_user.id
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard(),
    )


@dp.message(Command("delete_data"))
async def handle_delete_data_command(
    message: Message,
) -> None:
    await message.answer(
        text=(
            "🗑 <b>УДАЛЕНИЕ ДАННЫХ</b>\n\n"
            "Будут удалены:\n\n"
            "• сохранённые сообщения;\n"
            "• история удалений;\n"
            "• фотографии и видео;\n"
            "• голосовые и документы;\n"
            "• статистика.\n\n"
            "Подключение к автоматизации "
            "останется активным.\n\n"
            "Продолжить?"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=(
            get_delete_confirmation_keyboard()
        ),
    )


@dp.callback_query(F.data == "main_menu")
async def show_main_menu(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    if callback.message:
        await callback.message.edit_text(
            text=get_main_menu_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(),
        )


@dp.callback_query(F.data == "instructions")
async def show_instructions(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    if callback.message:
        await callback.message.edit_text(
            text=get_instructions_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard(),
        )


@dp.callback_query(F.data == "features")
async def show_features(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    if callback.message:
        await callback.message.edit_text(
            text=get_features_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard(),
        )


@dp.callback_query(F.data == "about")
async def show_about(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    if callback.message:
        await callback.message.edit_text(
            text=get_about_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard(),
        )


@dp.callback_query(F.data == "status")
async def show_status(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    if callback.message:
        await callback.message.edit_text(
            text=get_status_text(
                callback.from_user.id
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard(),
        )


@dp.callback_query(F.data == "statistics")
async def show_statistics(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    if callback.message:
        await callback.message.edit_text(
            text=get_statistics_text(
                callback.from_user.id
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard(),
        )


@dp.callback_query(F.data == "delete_data")
async def show_delete_confirmation(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    if callback.message:
        await callback.message.edit_text(
            text=(
                "🗑 <b>УДАЛЕНИЕ ДАННЫХ</b>\n\n"
                "Будут безвозвратно удалены:\n\n"
                "• все сохранённые сообщения;\n"
                "• история изменений и удалений;\n"
                "• фотографии, видео и файлы;\n"
                "• статистика пользователя.\n\n"
                "Подключение к автоматизации "
                "останется активным.\n\n"
                "Ты уверен?"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=(
                get_delete_confirmation_keyboard()
            ),
        )


@dp.callback_query(
    F.data == "confirm_delete_data"
)
async def confirm_delete_data(
    callback: CallbackQuery,
) -> None:
    await callback.answer(
        text="Удаляю данные..."
    )

    connection_ids = delete_user_messages(
        callback.from_user.id
    )

    delete_user_media(
        connection_ids
    )

    if callback.message:
        await callback.message.edit_text(
            text=(
                "✅ <b>ДАННЫЕ УДАЛЕНЫ</b>\n\n"
                "Все сохранённые сообщения, "
                "медиафайлы и статистика удалены.\n\n"
                "Подключение к автоматизации "
                "осталось активным.\n\n"
                "Новые входящие сообщения будут "
                "сохраняться как обычно."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard(),
        )


@dp.business_connection()
async def handle_business_connection(
    connection: BusinessConnection,
) -> None:
    save_business_connection(
        connection_id=connection.id,
        telegram_user_id=connection.user.id,
        user_chat_id=connection.user_chat_id,
        full_name=connection.user.full_name,
        is_enabled=connection.is_enabled,
        updated_at=current_time(),
    )

    if connection.is_enabled:
        await bot.send_message(
            chat_id=connection.user_chat_id,
            text=(
                "✅ <b>ПОДКЛЮЧЕНИЕ ВЫПОЛНЕНО</b>\n\n"
                "Message Tracker подключён "
                "к автоматизации чатов.\n\n"
                "🟢 Сохранение сообщений активно\n"
                "🟢 Сохранение медиа активно\n"
                "🟢 Уведомления активны"
            ),
            parse_mode=ParseMode.HTML,
        )

    else:
        await bot.send_message(
            chat_id=connection.user_chat_id,
            text=(
                "⚠️ <b>БОТ ОТКЛЮЧЁН</b>\n\n"
                "Автоматизация чатов отключена.\n\n"
                "Новые сообщения больше "
                "не будут сохраняться."
            ),
            parse_mode=ParseMode.HTML,
        )


@dp.business_message()
async def handle_business_message(
    message: Message,
) -> None:
    connection_id = (
        message.business_connection_id
    )

    if not connection_id:
        return

    owner_user_id = (
        get_connection_owner_user_id(
            connection_id
        )
    )

    owner_chat_id = (
        get_connection_owner_chat_id(
            connection_id
        )
    )

    if (
        owner_user_id is None
        or owner_chat_id is None
    ):
        return

    sender_id = get_sender_id(message)

    if sender_id == owner_user_id:
        if (
            message.reply_to_message
            is not None
            or message.external_reply
            is not None
        ):
            await try_extract_media_from_owner_reply(
                message=message,
                connection_id=connection_id,
                owner_chat_id=owner_chat_id,
            )

        return

    sender_name = get_sender_name(
        message
    )

    message_text = get_message_text(
        message
    )

    save_message(
        business_connection_id=connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        message_text=message_text,
        media_type=None,
        media_path=None,
        created_at=current_time(),
    )

    media_type, media_path = (
        await download_source_media(
            source=message,
            connection_id=connection_id,
            chat_id=message.chat.id,
            filename_id=message.message_id,
        )
    )

    save_message(
        business_connection_id=connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        message_text=message_text,
        media_type=media_type,
        media_path=media_path,
        created_at=current_time(),
    )


@dp.edited_business_message()
async def handle_edited_business_message(
    message: Message,
) -> None:
    connection_id = (
        message.business_connection_id
    )

    if not connection_id:
        return

    owner_user_id = (
        get_connection_owner_user_id(
            connection_id
        )
    )

    if owner_user_id is None:
        return

    sender_id = get_sender_id(message)

    if sender_id == owner_user_id:
        return

    old_message = get_message(
        business_connection_id=connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )

    sender_name = get_sender_name(
        message
    )

    new_text = get_message_text(
        message
    )

    media_type, media_path = (
        await download_source_media(
            source=message,
            connection_id=connection_id,
            chat_id=message.chat.id,
            filename_id=message.message_id,
        )
    )

    save_message(
        business_connection_id=connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        message_text=new_text,
        media_type=media_type,
        media_path=media_path,
        created_at=current_time(),
    )

    if old_message is None:
        return

    old_text = str(
        old_message.get(
            "message_text"
        )
        or ""
    )

    if old_text == new_text:
        return

    owner_chat_id = (
        get_connection_owner_chat_id(
            connection_id
        )
    )

    if owner_chat_id is None:
        return

    safe_sender = escape(
        str(
            old_message.get(
                "sender_name"
            )
            or sender_name
        )
    )

    await bot.send_message(
        chat_id=owner_chat_id,
        text=(
            "✏️ <b>СООБЩЕНИЕ ИЗМЕНЕНО</b>\n\n"
            f"👤 <b>Отправитель:</b>\n"
            f"{safe_sender}\n\n"
            f"📄 <b>Было:</b>\n"
            f"<blockquote>"
            f"{escape(old_text)}"
            f"</blockquote>\n\n"
            f"📝 <b>Стало:</b>\n"
            f"<blockquote>"
            f"{escape(new_text)}"
            f"</blockquote>\n\n"
            f"🕒 <b>Зафиксировано:</b> "
            f"{formatted_time()}"
        ),
        parse_mode=ParseMode.HTML,
    )


@dp.deleted_business_messages()
async def handle_deleted_business_messages(
    deleted: BusinessMessagesDeleted,
) -> None:
    connection_id = (
        deleted.business_connection_id
    )

    owner_chat_id = (
        get_connection_owner_chat_id(
            connection_id
        )
    )

    if owner_chat_id is None:
        return

    deletion_time = current_time()

    for message_id in deleted.message_ids:
        saved_message = None

        for _ in range(10):
            saved_message = get_message(
                business_connection_id=(
                    connection_id
                ),
                chat_id=deleted.chat.id,
                message_id=message_id,
            )

            if saved_message is not None:
                break

            await asyncio.sleep(0.5)

        if saved_message is None:
            continue

        sender_name = escape(
            str(
                saved_message.get(
                    "sender_name"
                )
                or "Неизвестный"
            )
        )

        saved_text = escape(
            str(
                saved_message.get(
                    "message_text"
                )
                or ""
            )
        )

        await bot.send_message(
            chat_id=owner_chat_id,
            text=(
                "🗑 <b>СООБЩЕНИЕ УДАЛЕНО</b>\n\n"
                f"👤 <b>Отправитель:</b>\n"
                f"{sender_name}\n\n"
                f"💬 <b>Содержимое:</b>\n"
                f"<blockquote>"
                f"{saved_text}"
                f"</blockquote>\n\n"
                f"🕒 <b>Зафиксировано:</b> "
                f"{formatted_time()}"
            ),
            parse_mode=ParseMode.HTML,
        )

        await send_saved_deleted_media(
            owner_chat_id=owner_chat_id,
            saved_message=saved_message,
        )

        mark_message_deleted(
            business_connection_id=(
                connection_id
            ),
            chat_id=deleted.chat.id,
            message_id=message_id,
            deleted_at=deletion_time,
        )


async def main() -> None:
    create_tables()

    MEDIA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    await bot.set_my_commands(
        commands=[
            BotCommand(
                command="start",
                description=(
                    "Открыть главное меню"
                ),
            ),
            BotCommand(
                command="status",
                description=(
                    "Проверить подключение"
                ),
            ),
            BotCommand(
                command="statistics",
                description=(
                    "Посмотреть статистику"
                ),
            ),
            BotCommand(
                command="help",
                description=(
                    "Инструкция по подключению"
                ),
            ),
            BotCommand(
                command="features",
                description=(
                    "Возможности бота"
                ),
            ),
            BotCommand(
                command="delete_data",
                description=(
                    "Удалить мои данные"
                ),
            ),
        ]
    )

    print("Message Tracker запущен")
    print(
        "Ожидаю сообщения "
        "и события Telegram"
    )

    await bot.delete_webhook(
        drop_pending_updates=True,
    )

    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
        ],
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print(
            "Message Tracker остановлен"
        )