import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def generate_key() -> str:
    """
    Генерирует AES-256 ключ и возвращает его в base64.
    Используется для MASTER_KEK или пользовательского DEK.
    """
    key = AESGCM.generate_key(bit_length=256)
    return base64.urlsafe_b64encode(key).decode("utf-8")


def key_from_base64(key_b64: str) -> bytes:
    """
    Преобразует base64-ключ обратно в bytes.
    """
    return base64.urlsafe_b64decode(key_b64.encode("utf-8"))


def encrypt_bytes(
    data: bytes,
    key: bytes,
    associated_data: bytes | None = None,
) -> tuple[bytes, bytes]:
    """
    Шифрует bytes через AES-256-GCM.

    Возвращает:
    nonce,
    ciphertext
    """
    nonce = os.urandom(12)

    aes = AESGCM(key)

    encrypted = aes.encrypt(
        nonce,
        data,
        associated_data,
    )

    return nonce, encrypted


def decrypt_bytes(
    encrypted_data: bytes,
    nonce: bytes,
    key: bytes,
    associated_data: bytes | None = None,
) -> bytes:
    """
    Расшифровывает bytes через AES-256-GCM.
    """
    aes = AESGCM(key)

    return aes.decrypt(
        nonce,
        encrypted_data,
        associated_data,
    )


def encrypt_text(
    text: str,
    key: bytes,
) -> tuple[bytes, bytes]:
    """
    Шифрует обычный текст.
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
    Расшифровывает текст.
    """
    plaintext = decrypt_bytes(
        encrypted_text,
        nonce,
        key,
        b"telegram-message-v1",
    )

    return plaintext.decode("utf-8")


def encrypt_dek(
    dek: bytes,
    master_kek: bytes,
) -> tuple[bytes, bytes]:
    """
    Шифрует пользовательский DEK мастер-ключом KEK.
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
    Расшифровывает пользовательский DEK.
    """
    return decrypt_bytes(
        encrypted_dek,
        nonce,
        master_kek,
        b"telegram-user-dek-v1",
    )


def generate_dek() -> bytes:
    """
    Создаёт отдельный AES-256 DEK для пользователя.
    """
    return AESGCM.generate_key(bit_length=256)