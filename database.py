import sqlite3
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "messages.db"


def create_tables() -> None:
    with sqlite3.connect(DB_PATH) as connection:
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
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_connection_id TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                sender_id INTEGER,
                sender_name TEXT,
                message_text TEXT,
                media_type TEXT,
                media_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                deleted_at TEXT,

                UNIQUE (
                    business_connection_id,
                    chat_id,
                    message_id
                )
            )
            """
        )


def save_business_connection(
    connection_id: str,
    telegram_user_id: int,
    user_chat_id: int,
    full_name: str,
    is_enabled: bool,
    updated_at: str,
) -> None:
    with sqlite3.connect(DB_PATH) as connection:
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
                telegram_user_id = excluded.telegram_user_id,
                user_chat_id = excluded.user_chat_id,
                full_name = excluded.full_name,
                is_enabled = excluded.is_enabled,
                updated_at = excluded.updated_at
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


def get_connection_owner_user_id(
    connection_id: str,
) -> int | None:
    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            """
            SELECT telegram_user_id
            FROM business_connections
            WHERE connection_id = ?
              AND is_enabled = 1
            """,
            (connection_id,),
        ).fetchone()

    return int(row[0]) if row else None


def get_connection_owner_chat_id(
    connection_id: str,
) -> int | None:
    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            """
            SELECT user_chat_id
            FROM business_connections
            WHERE connection_id = ?
              AND is_enabled = 1
            """,
            (connection_id,),
        ).fetchone()

    return int(row[0]) if row else None


def get_user_connection(
    user_chat_id: int,
) -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row

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

    return dict(row) if row else None


def get_user_connection_ids(
    user_chat_id: int,
) -> list[str]:
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT connection_id
            FROM business_connections
            WHERE user_chat_id = ?
            """,
            (user_chat_id,),
        ).fetchall()

    return [str(row[0]) for row in rows]


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
) -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO messages (
                business_connection_id,
                chat_id,
                message_id,
                sender_id,
                sender_name,
                message_text,
                media_type,
                media_path,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT (
                business_connection_id,
                chat_id,
                message_id
            )
            DO UPDATE SET
                sender_id = excluded.sender_id,
                sender_name = excluded.sender_name,
                message_text = excluded.message_text,

                media_type = COALESCE(
                    excluded.media_type,
                    messages.media_type
                ),

                media_path = COALESCE(
                    excluded.media_path,
                    messages.media_path
                ),

                updated_at = excluded.created_at
            """,
            (
                business_connection_id,
                chat_id,
                message_id,
                sender_id,
                sender_name,
                message_text,
                media_type,
                media_path,
                created_at,
            ),
        )


def get_message(
    business_connection_id: str,
    chat_id: int,
    message_id: int,
) -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row

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

    return dict(row) if row else None


def mark_message_deleted(
    business_connection_id: str,
    chat_id: int,
    message_id: int,
    deleted_at: str,
) -> None:
    with sqlite3.connect(DB_PATH) as connection:
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


def get_user_statistics(
    user_chat_id: int,
) -> dict[str, int]:
    connection = get_user_connection(user_chat_id)

    empty_statistics = {
        "total_messages": 0,
        "deleted_messages": 0,
        "media_messages": 0,
        "unique_chats": 0,
    }

    if connection is None:
        return empty_statistics

    connection_id = connection["connection_id"]

    with sqlite3.connect(DB_PATH) as database:
        row = database.execute(
            """
            SELECT
                COUNT(*) AS total_messages,

                SUM(
                    CASE
                        WHEN deleted_at IS NOT NULL THEN 1
                        ELSE 0
                    END
                ) AS deleted_messages,

                SUM(
                    CASE
                        WHEN media_type IS NOT NULL THEN 1
                        ELSE 0
                    END
                ) AS media_messages,

                COUNT(DISTINCT chat_id) AS unique_chats

            FROM messages
            WHERE business_connection_id = ?
            """,
            (connection_id,),
        ).fetchone()

    if row is None:
        return empty_statistics

    return {
        "total_messages": int(row[0] or 0),
        "deleted_messages": int(row[1] or 0),
        "media_messages": int(row[2] or 0),
        "unique_chats": int(row[3] or 0),
    }


def delete_user_messages(
    user_chat_id: int,
) -> list[str]:
    connection_ids = get_user_connection_ids(user_chat_id)

    if not connection_ids:
        return []

    placeholders = ",".join(
        "?" for _ in connection_ids
    )

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            f"""
            DELETE FROM messages
            WHERE business_connection_id
            IN ({placeholders})
            """,
            connection_ids,
        )

    return connection_ids