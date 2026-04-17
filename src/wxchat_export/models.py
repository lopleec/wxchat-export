from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AccountRef:
    account_id: str
    account_dir: Path
    cleaned_wxid: str


@dataclass(frozen=True)
class SessionRef:
    username: str
    display_name: str
    is_chatroom: bool
    last_timestamp: int


@dataclass(frozen=True)
class ExportMessage:
    session_username: str
    sort_seq: int
    create_time: int
    sender_username: str
    sender_display_name: str
    kind: str
    text: str


@dataclass(frozen=True)
class HookCandidate:
    file_offset: int
    vmaddr: int
    register: int
    preceding_branch_offsets: tuple[int, ...]
