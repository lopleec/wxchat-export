from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

from .models import AccountRef, ExportMessage, SessionRef
from .sqlcipher import SQLCipherClient
from .text_utils import classify_message


def _quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class WeChatRepository:
    def __init__(self, account: AccountRef, key_hex: str, sqlcipher: SQLCipherClient) -> None:
        self.account = account
        self.key_hex = key_hex
        self.sqlcipher = sqlcipher
        self.session_db = account.account_dir / "db_storage/session/session.db"
        self.contact_db = account.account_dir / "db_storage/contact/contact.db"
        self.message_dir = account.account_dir / "db_storage/message"
        self._display_map: dict[str, str] | None = None
        self._fallback_titles: dict[str, str] | None = None

    def probe(self) -> None:
        self.sqlcipher.probe(self.session_db, self.key_hex)
        message_db = self.message_databases()[0]
        self.sqlcipher.probe(message_db, self.key_hex)

    def message_databases(self) -> list[Path]:
        results: list[Path] = []
        if not self.message_dir.exists():
            return results
        for path in sorted(self.message_dir.glob("message_*.db")):
            if path.name.endswith(("-wal", "-shm")):
                continue
            if path.suffix != ".db":
                continue
            stem = path.stem
            tail = stem.split("_", 1)[1]
            if tail.isdigit():
                results.append(path)
        return results

    def _load_display_maps(self) -> dict[str, str]:
        if self._display_map is not None:
            return self._display_map

        display_map: dict[str, str] = {}
        for table in ("contact", "stranger"):
            rows = self.sqlcipher.query_json(
                self.contact_db,
                self.key_hex,
                f"""
                SELECT
                  COALESCE(username, '') AS username,
                  COALESCE(remark, '') AS remark,
                  COALESCE(nick_name, '') AS nick_name
                FROM {table};
                """,
            )
            for row in rows:
                username = row.get("username", "")
                if not username:
                    continue
                display_name = row.get("remark") or row.get("nick_name") or username
                display_map.setdefault(username, display_name)

        self._display_map = display_map
        return display_map

    def _load_fallback_titles(self) -> dict[str, str]:
        if self._fallback_titles is not None:
            return self._fallback_titles
        rows = self.sqlcipher.query_json(
            self.session_db,
            self.key_hex,
            """
            SELECT
              COALESCE(username, '') AS username,
              COALESCE(session_title, '') AS session_title
            FROM SessionNoContactInfoTable;
            """,
        )
        self._fallback_titles = {
            row["username"]: row["session_title"]
            for row in rows
            if row.get("username") and row.get("session_title")
        }
        return self._fallback_titles

    def _display_name_for_username(self, username: str) -> str:
        display_map = self._load_display_maps()
        fallback_titles = self._load_fallback_titles()
        return display_map.get(username) or fallback_titles.get(username) or username

    def list_sessions(self) -> list[SessionRef]:
        rows = self.sqlcipher.query_json(
            self.session_db,
            self.key_hex,
            """
            SELECT
              COALESCE(username, '') AS username,
              COALESCE(last_timestamp, 0) AS last_timestamp,
              COALESCE(sort_timestamp, 0) AS sort_timestamp
            FROM SessionTable
            ORDER BY sort_timestamp DESC, last_timestamp DESC, username ASC;
            """,
        )
        sessions: list[SessionRef] = []
        for row in rows:
            username = row.get("username", "")
            if not username:
                continue
            sessions.append(
                SessionRef(
                    username=username,
                    display_name=self._display_name_for_username(username),
                    is_chatroom=username.endswith("@chatroom"),
                    last_timestamp=int(row.get("last_timestamp") or 0),
                )
            )
        return sessions

    def _message_table_name(self, session_username: str) -> str:
        digest = hashlib.md5(session_username.encode("utf-8")).hexdigest()
        return f"Msg_{digest}"

    def _message_table_exists(self, db_path: Path, table_name: str) -> bool:
        rows = self.sqlcipher.query_json(
            db_path,
            self.key_hex,
            f"""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = {_quote_sql_string(table_name)}
            LIMIT 1;
            """,
        )
        return bool(rows)

    def load_messages(self, session: SessionRef) -> list[ExportMessage]:
        table_name = self._message_table_name(session.username)
        messages: list[ExportMessage] = []
        for db_path in self.message_databases():
            if not self._message_table_exists(db_path, table_name):
                continue
            escaped_session = _quote_sql_string(session.username)
            rows = self.sqlcipher.query_json(
                db_path,
                self.key_hex,
                f"""
                WITH session_row AS (
                  SELECT rowid AS session_rowid
                  FROM Name2Id
                  WHERE user_name = {escaped_session}
                  LIMIT 1
                )
                SELECT
                  m.local_id AS local_id,
                  COALESCE(m.server_id, 0) AS server_id,
                  COALESCE(m.local_type, 0) AS local_type,
                  COALESCE(m.sort_seq, 0) AS sort_seq,
                  COALESCE(m.real_sender_id, 0) AS real_sender_id,
                  COALESCE(m.create_time, 0) AS create_time,
                  COALESCE(m.status, 0) AS status,
                  COALESCE(m.source, '') AS source,
                  COALESCE(m.message_content, '') AS message_content,
                  COALESCE(m.compress_content, '') AS compress_content,
                  COALESCE(sender.user_name, '') AS sender_username,
                  CASE
                    WHEN send.msg_local_id IS NULL THEN 0
                    ELSE 1
                  END AS is_outgoing
                FROM "{table_name}" AS m
                LEFT JOIN Name2Id AS sender
                  ON m.real_sender_id = sender.rowid
                LEFT JOIN session_row AS session_ref
                  ON 1 = 1
                LEFT JOIN SendInfo AS send
                  ON send.chat_name_id = session_ref.session_rowid
                 AND send.msg_local_id = m.local_id
                ORDER BY m.sort_seq ASC, m.create_time ASC, m.local_id ASC;
                """,
            )
            for row in rows:
                messages.append(self._to_export_message(session, row))

        messages.sort(key=lambda item: (item.sort_seq, item.create_time))
        return messages

    def _sender_for_row(self, session: SessionRef, row: dict) -> tuple[str, str]:
        display_map = self._load_display_maps()
        sender_username = (row.get("sender_username") or "").strip()
        is_outgoing = bool(row.get("is_outgoing"))

        if is_outgoing:
            return self.account.cleaned_wxid, "我"

        if session.is_chatroom:
            if sender_username:
                return sender_username, display_map.get(sender_username, sender_username)
            return "", session.display_name

        if sender_username:
            if sender_username == self.account.cleaned_wxid:
                return sender_username, "我"
            return sender_username, display_map.get(sender_username, session.display_name)
        return session.username, session.display_name

    def _to_export_message(self, session: SessionRef, row: dict) -> ExportMessage:
        kind, text = classify_message(
            int(row.get("local_type") or 0),
            row.get("message_content") or "",
            row.get("compress_content") or "",
        )
        sender_username, sender_display_name = self._sender_for_row(session, row)
        return ExportMessage(
            session_username=session.username,
            sort_seq=int(row.get("sort_seq") or 0),
            create_time=int(row.get("create_time") or 0),
            sender_username=sender_username,
            sender_display_name=sender_display_name,
            kind=kind,
            text=text,
        )

    @staticmethod
    def export_message_to_dict(message: ExportMessage) -> dict:
        return asdict(message)
