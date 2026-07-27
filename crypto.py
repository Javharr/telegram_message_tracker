import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


# =========================================================
# KEY GENERATION
# =========================================================


def generate_key() -> str:
    """
    Генерирует случайный AES-256 ключ.

    Возвращает ключ в Base64-формате.
    """
    key = AESGCM.generate_key(bit_length=256)

    return base64.urlsafe_b64encode(
        key
    ).decode("utf-8")


def generate_dek() -> bytes:
    """
    Генерирует отдельный AES-256 DEK.

    DEK используется для шифрования данных
    конкретного пользователя.
    """
    return AESGCM.generate_key(
        bit_length=256
    )


# =========================================================
# BASE64
# =========================================================


def key_from_base64(
    key_b64: str,
) -> bytes:
    """
    Преобразует Base64-ключ обратно в bytes.
    """
    return base64.urlsafe_b64decode(
        key_b64.encode("utf-8")
    )


# =========================================================
# MASTER KEK
# =========================================================


def derive_master_kek(
    part_a: str,
    part_b: bytes,
) -> bytes:
    """
    Собирает MASTER KEK из двух независимых частей.

    KEY_PART_A:
        хранится в .env

    KEY_PART_B:
        хранится отдельно от проекта
        в ~/.message_tracker/key.part

    Готовый MASTER KEK нигде не сохраняется.
    Он создаётся только во время работы приложения.
    """

    material = (
        part_a.encode("utf-8")
        + b":"
        + part_b
    )

    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,

        salt=(
            b"telegram-message-"
            b"tracker-v1"
        ),

        info=b"master-kek",

    ).derive(material)


# =========================================================
# BASIC AES-256-GCM
# =========================================================


def encrypt_bytes(
    data: bytes,
    key: bytes,
    associated_data: bytes | None = None,
) -> tuple[bytes, bytes]:
    """
    Шифрует bytes через AES-256-GCM.

    Возвращает:
        nonce
        ciphertext
    """

    nonce = os.urandom(12)

    aes = AESGCM(key)

    encrypted_data = aes.encrypt(
        nonce,
        data,
        associated_data,
    )

    return (
        nonce,
        encrypted_data,
    )


def decrypt_bytes(
    encrypted_data: bytes,
    nonce: bytes,
    key: bytes,
    associated_data: bytes | None = None,
) -> bytes:
    """
    Расшифровывает AES-256-GCM данные.
    """

    aes = AESGCM(key)

    return aes.decrypt(
        nonce,
        encrypted_data,
        associated_data,
    )


# =========================================================
# TEXT
# =========================================================


def encrypt_text(
    text: str,
    key: bytes,
) -> tuple[bytes, bytes]:
    """
    Шифрует текст Telegram-сообщения.
    """

    return encrypt_bytes(
        text.encode("utf-8"),
        key,
        b"telegram-message-v1",
    )


def decrypt_text(
    encrypted_text: bytes,
    nonce: bytes,
    key: bytes,
) -> str:
    """
    Расшифровывает текст Telegram-сообщения.
    """

    plaintext = decrypt_bytes(
        encrypted_text,
        nonce,
        key,
        b"telegram-message-v1",
    )

    return plaintext.decode("utf-8")


# =========================================================
# USER DEK
# =========================================================


def encrypt_dek(
    dek: bytes,
    master_kek: bytes,
) -> tuple[bytes, bytes]:
    """
    Шифрует пользовательский DEK через MASTER KEK.

    Открытый DEK в БД никогда не сохраняется.
    """

    return encrypt_bytes(
        dek,
        master_kek,
        b"telegram-user-dek-v1",
    )


def decrypt_dek(
    encrypted_dek: bytes,
    nonce: bytes,
    master_kek: bytes,
) -> bytes:
    """
    Расшифровывает DEK пользователя.
    """

    return decrypt_bytes(
        encrypted_dek,
        nonce,
        master_kek,
        b"telegram-user-dek-v1",
    )


# =========================================================
# MEDIA
# =========================================================


def encrypt_media(
    media_data: bytes,
    dek: bytes,
) -> tuple[bytes, bytes]:
    """
    Шифрует фото, голосовые, видео,
    документы и другие Telegram media.
    """

    return encrypt_bytes(
        media_data,
        dek,
        b"telegram-media-v1",
    )


def decrypt_media(
    encrypted_media: bytes,
    nonce: bytes,
    dek: bytes,
) -> bytes:
    """
    Расшифровывает Telegram media.
    """

    return decrypt_bytes(
        encrypted_media,
        nonce,
        dek,
        b"telegram-media-v1",
    )