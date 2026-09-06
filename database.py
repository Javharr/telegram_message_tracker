import sqlite3
from pathlib import Path
from typing import Any

from config import ENCRYPTION_KEY
from crypto import (
    decrypt_dek,
    decrypt_text,
    derive_master_kek,
    encrypt_dek,
    encrypt_text,
    generate_dek,
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "messages.db"


# =========================================================
# MASTER KEK
# =========================================================

MASTER_KEK_BYTES = derive_master_kek(ENCRYPTION_KEY)


# =========================================================
# DATABASE CONNECTION
# =========================================================


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def column_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        row["name"] == column_name
        for row in rows
    )


# =========================================================
# TABLES
# =========================================================


def create_tables() -> None:
    with get_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS business_connections (
                connection_id TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                user_chat_id INTEGER NOT NULL,
                full_name TEXT,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_keys (
                telegram_user_id INTEGER PRIMARY KEY,

                encrypted_dek BLOB NOT NULL,
                dek_nonce BLOB NOT NULL,

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                business_connection_id TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,

                sender_id INTEGER,

                sender_name TEXT,
                message_text TEXT,

                encrypted_sender_name BLOB,
                sender_name_nonce BLOB,

                encrypted_message_text BLOB,
                message_text_nonce BLOB,

                media_type TEXT,
                media_path TEXT,

                created_at TEXT NOT NULL,
                updated_at TEXT,
                deleted_at TEXT,

                reply_to_message_id INTEGER,

                UNIQUE (
                    business_connection_id,
                    chat_id,
                    message_id
                )
            )
            """
        )

        migrate_database(connection)


# =========================================================
# MIGRATION
# =========================================================


def migrate_database(
    connection: sqlite3.Connection,
) -> None:
    """
    Добавляет encryption-поля в старую БД и
    переносит старые plaintext сообщения в encrypted поля.
    """

    required_columns = {
        "encrypted_sender_name": "BLOB",
        "sender_name_nonce": "BLOB",
        "encrypted_message_text": "BLOB",
        "message_text_nonce": "BLOB",
        "reply_to_message_id": "INTEGER",
    }

    for column_name, column_type in required_columns.items():

        if not column_exists(
            connection,
            "messages",
            column_name,
        ):
            connection.execute(
                f"""
                ALTER TABLE messages
                ADD COLUMN {column_name} {column_type}
                """
            )

    rows = connection.execute(
        """
        SELECT
            m.id,
            m.business_connection_id,
            m.sender_name,
            m.message_text,

            m.encrypted_sender_name,
            m.encrypted_message_text,

            bc.telegram_user_id

        FROM messages m

        LEFT JOIN business_connections bc
            ON bc.connection_id =
               m.business_connection_id

        WHERE
            (
                m.sender_name IS NOT NULL
                AND m.encrypted_sender_name IS NULL
            )

            OR

            (
                m.message_text IS NOT NULL
                AND m.encrypted_message_text IS NULL
            )
        """
    ).fetchall()

    for row in rows:

        telegram_user_id = row["telegram_user_id"]

        # Если старое сообщение невозможно привязать
        # к владельцу business connection — пропускаем.
        if telegram_user_id is None:
            continue

        dek = get_or_create_user_dek(
            int(telegram_user_id),
            connection=connection,
        )

        encrypted_sender_name = None
        sender_name_nonce = None

        encrypted_message_text = None
        message_text_nonce = None

        if row["sender_name"] is not None:

            (
                sender_name_nonce,
                encrypted_sender_name,
            ) = encrypt_text(
                str(row["sender_name"]),
                dek,
            )

        if row["message_text"] is not None:

            (
                message_text_nonce,
                encrypted_message_text,
            ) = encrypt_text(
                str(row["message_text"]),
                dek,
            )

        connection.execute(
            """
            UPDATE messages

            SET
                encrypted_sender_name = ?,
                sender_name_nonce = ?,

                encrypted_message_text = ?,
                message_text_nonce = ?,

                sender_name = NULL,
                message_text = NULL

            WHERE id = ?
            """,
            (
                encrypted_sender_name,
                sender_name_nonce,

                encrypted_message_text,
                message_text_nonce,

                row["id"],
            ),
        )


# =========================================================
# USER KEYS
# =========================================================


def get_or_create_user_dek(
    telegram_user_id: int,
    connection: sqlite3.Connection | None = None,
) -> bytes:
    """
    Создаёт отдельный DEK для каждого пользователя.

    Открытый DEK никогда не сохраняется в БД.
    В БД хранится только encrypted_dek.
    """

    own_connection = connection is None

    if own_connection:
        connection = get_connection()

    assert connection is not None

    try:

        row = connection.execute(
            """
            SELECT
                encrypted_dek,
                dek_nonce

            FROM user_keys

            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        ).fetchone()

        if row is not None:

            return decrypt_dek(
                encrypted_dek=row["encrypted_dek"],
                nonce=row["dek_nonce"],
                master_kek=MASTER_KEK_BYTES,
            )

        # Новый пользователь — создаём его DEK.
        dek = generate_dek()

        (
            dek_nonce,
            encrypted_dek_value,
        ) = encrypt_dek(
            dek,
            MASTER_KEK_BYTES,
        )

        connection.execute(
            """
            INSERT INTO user_keys (
                telegram_user_id,
                encrypted_dek,
                dek_nonce
            )
            VALUES (?, ?, ?)
            """,
            (
                telegram_user_id,
                encrypted_dek_value,
                dek_nonce,
            ),
        )

        if own_connection:
            connection.commit()

        return dek

    finally:

        if own_connection:
            connection.close()


def get_dek_by_connection_id(
    business_connection_id: str,
) -> bytes:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT telegram_user_id

            FROM business_connections

            WHERE connection_id = ?
            """,
            (business_connection_id,),
        ).fetchone()

        if row is None:
            raise RuntimeError(
                "Business connection не найдена"
            )

        telegram_user_id = int(
            row["telegram_user_id"]
        )

        return get_or_create_user_dek(
            telegram_user_id,
            connection=connection,
        )


# =========================================================
# BUSINESS CONNECTIONS
# =========================================================


def save_business_connection(
    connection_id: str,
    telegram_user_id: int,
    user_chat_id: int,
    full_name: str,
    is_enabled: bool,
    updated_at: str,
) -> None:

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO business_connections (
                connection_id,
                telegram_user_id,
                user_chat_id,
                full_name,
                is_enabled,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT (connection_id)

            DO UPDATE SET
                telegram_user_id =
                    excluded.telegram_user_id,

                user_chat_id =
                    excluded.user_chat_id,

                full_name =
                    excluded.full_name,

                is_enabled =
                    excluded.is_enabled,

                updated_at =
                    excluded.updated_at
            """,
            (
                connection_id,
                telegram_user_id,
                user_chat_id,
                full_name,
                int(is_enabled),
                updated_at,
            ),
        )

        # Создаём пользовательский DEK,
        # если его ещё нет.
        get_or_create_user_dek(
            telegram_user_id,
            connection=connection,
        )


def get_connection_owner_user_id(
    connection_id: str,
) -> int | None:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT telegram_user_id

            FROM business_connections

            WHERE connection_id = ?
              AND is_enabled = 1
            """,
            (connection_id,),
        ).fetchone()

    if row is None:
        return None

    return int(
        row["telegram_user_id"]
    )


def get_connection_owner_chat_id(
    connection_id: str,
) -> int | None:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT user_chat_id

            FROM business_connections

            WHERE connection_id = ?
              AND is_enabled = 1
            """,
            (connection_id,),
        ).fetchone()

    if row is None:
        return None

    return int(
        row["user_chat_id"]
    )


def get_user_connection(
    user_chat_id: int,
) -> dict[str, Any] | None:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT *

            FROM business_connections

            WHERE user_chat_id = ?

            ORDER BY updated_at DESC

            LIMIT 1
            """,
            (user_chat_id,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def get_user_connection_ids(
    user_chat_id: int,
) -> list[str]:

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT connection_id

            FROM business_connections

            WHERE user_chat_id = ?
            """,
            (user_chat_id,),
        ).fetchall()

    return [
        str(row["connection_id"])
        for row in rows
    ]


# =========================================================
# SAVE MESSAGE
# =========================================================


def save_message(
    business_connection_id: str,
    chat_id: int,
    message_id: int,
    sender_id: int | None,
    sender_name: str,
    message_text: str,
    media_type: str | None,
    media_path: str | None,
    created_at: str,
    reply_to_message_id: int | None = None,
) -> None:

    dek = get_dek_by_connection_id(
        business_connection_id
    )

    # Шифруем имя отправителя.
    (
        sender_name_nonce,
        encrypted_sender_name,
    ) = encrypt_text(
        sender_name,
        dek,
    )

    # Шифруем текст сообщения.
    (
        message_text_nonce,
        encrypted_message_text,
    ) = encrypt_text(
        message_text,
        dek,
    )

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO messages (
                business_connection_id,
                chat_id,
                message_id,

                sender_id,

                sender_name,
                message_text,

                encrypted_sender_name,
                sender_name_nonce,

                encrypted_message_text,
                message_text_nonce,

                media_type,
                media_path,

                created_at,

                reply_to_message_id
            )

            VALUES (
                ?, ?, ?,
                ?,
                NULL, NULL,
                ?, ?,
                ?, ?,
                ?, ?,
                ?,
                ?
            )

            ON CONFLICT (
                business_connection_id,
                chat_id,
                message_id
            )

            DO UPDATE SET

                sender_id =
                    excluded.sender_id,

                sender_name = NULL,
                message_text = NULL,

                encrypted_sender_name =
                    excluded.encrypted_sender_name,

                sender_name_nonce =
                    excluded.sender_name_nonce,

                encrypted_message_text =
                    excluded.encrypted_message_text,

                message_text_nonce =
                    excluded.message_text_nonce,

                media_type = COALESCE(
                    excluded.media_type,
                    messages.media_type
                ),

                media_path = COALESCE(
                    excluded.media_path,
                    messages.media_path
                ),

                reply_to_message_id =
                    COALESCE(
                        excluded.reply_to_message_id,
                        messages.reply_to_message_id
                    ),

                updated_at =
                    excluded.created_at
            """,
            (
                business_connection_id,
                chat_id,
                message_id,

                sender_id,

                encrypted_sender_name,
                sender_name_nonce,

                encrypted_message_text,
                message_text_nonce,

                media_type,
                media_path,

                created_at,

                reply_to_message_id,
            ),
        )


# =========================================================
# GET MESSAGE
# =========================================================


def get_message(
    business_connection_id: str,
    chat_id: int,
    message_id: int,
) -> dict[str, Any] | None:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT *

            FROM messages

            WHERE business_connection_id = ?
              AND chat_id = ?
              AND message_id = ?
            """,
            (
                business_connection_id,
                chat_id,
                message_id,
            ),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    dek = get_dek_by_connection_id(
        business_connection_id
    )

    # ---------------------------
    # Sender name
    # ---------------------------

    encrypted_sender_name = result.get(
        "encrypted_sender_name"
    )

    sender_name_nonce = result.get(
        "sender_name_nonce"
    )

    if (
        encrypted_sender_name is not None
        and sender_name_nonce is not None
    ):

        result["sender_name"] = decrypt_text(
            encrypted_sender_name,
            sender_name_nonce,
            dek,
        )

    # ---------------------------
    # Message text
    # ---------------------------

    encrypted_message_text = result.get(
        "encrypted_message_text"
    )

    message_text_nonce = result.get(
        "message_text_nonce"
    )

    if (
        encrypted_message_text is not None
        and message_text_nonce is not None
    ):

        result["message_text"] = decrypt_text(
            encrypted_message_text,
            message_text_nonce,
            dek,
        )

    # Ciphertext наружу не отдаём.

    result.pop(
        "encrypted_sender_name",
        None,
    )

    result.pop(
        "sender_name_nonce",
        None,
    )

    result.pop(
        "encrypted_message_text",
        None,
    )

    result.pop(
        "message_text_nonce",
        None,
    )

    return result


# =========================================================
# MARK DELETED
# =========================================================


def mark_message_deleted(
    business_connection_id: str,
    chat_id: int,
    message_id: int,
    deleted_at: str,
) -> None:

    with get_connection() as connection:

        connection.execute(
            """
            UPDATE messages

            SET deleted_at = ?

            WHERE business_connection_id = ?
              AND chat_id = ?
              AND message_id = ?
            """,
            (
                deleted_at,
                business_connection_id,
                chat_id,
                message_id,
            ),
        )


# =========================================================
# STATISTICS
# =========================================================


def get_user_statistics(
    user_chat_id: int,
) -> dict[str, int]:

    connection_info = get_user_connection(
        user_chat_id
    )

    empty_statistics = {
        "total_messages": 0,
        "deleted_messages": 0,
        "media_messages": 0,
        "unique_chats": 0,
    }

    if connection_info is None:
        return empty_statistics

    connection_id = connection_info[
        "connection_id"
    ]

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT

                COUNT(*) AS total_messages,

                SUM(
                    CASE
                        WHEN deleted_at IS NOT NULL
                        THEN 1
                        ELSE 0
                    END
                ) AS deleted_messages,

                SUM(
                    CASE
                        WHEN media_type IS NOT NULL
                        THEN 1
                        ELSE 0
                    END
                ) AS media_messages,

                COUNT(
                    DISTINCT chat_id
                ) AS unique_chats

            FROM messages

            WHERE business_connection_id = ?
            """,
            (connection_id,),
        ).fetchone()

    if row is None:
        return empty_statistics

    return {
        "total_messages":
            int(row["total_messages"] or 0),

        "deleted_messages":
            int(row["deleted_messages"] or 0),

        "media_messages":
            int(row["media_messages"] or 0),

        "unique_chats":
            int(row["unique_chats"] or 0),
    }


# =========================================================
# DELETE USER DATA
# =========================================================


def delete_user_messages(
    user_chat_id: int,
) -> list[str]:

    connection_ids = get_user_connection_ids(
        user_chat_id
    )

    if not connection_ids:
        return []

    placeholders = ",".join(
        "?"
        for _ in connection_ids
    )

    with get_connection() as connection:

        connection.execute(
            f"""
            DELETE FROM messages

            WHERE business_connection_id
            IN ({placeholders})
            """,
            connection_ids,
        )

    return connection_ids