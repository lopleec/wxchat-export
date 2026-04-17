from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import AccountRef, ExportMessage, SessionRef
from .text_utils import format_timestamp, sanitize_filename_component


def _session_basename(session: SessionRef) -> str:
    return f"{sanitize_filename_component(session.display_name)}__{sanitize_filename_component(session.username)}"


def write_session_exports(
    out_dir: Path,
    account: AccountRef,
    session: SessionRef,
    messages: list[ExportMessage],
    export_format: str,
) -> dict[str, str]:
    sessions_dir = out_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    base_name = _session_basename(session)
    outputs: dict[str, str] = {}

    if export_format in {"md", "both"}:
        md_path = sessions_dir / f"{base_name}.md"
        _write_markdown(md_path, account, session, messages)
        outputs["md"] = str(md_path)

    if export_format in {"jsonl", "both"}:
        jsonl_path = sessions_dir / f"{base_name}.jsonl"
        _write_jsonl(jsonl_path, messages)
        outputs["jsonl"] = str(jsonl_path)

    return outputs


def _write_markdown(
    path: Path,
    account: AccountRef,
    session: SessionRef,
    messages: list[ExportMessage],
) -> None:
    header = [
        f"# {session.display_name}",
        "",
        f"- Account: {account.account_id}",
        f"- Account WXID: {account.cleaned_wxid}",
        f"- Session Username: {session.username}",
        f"- Exported At: {datetime.now().isoformat(timespec='seconds')}",
        f"- Total Messages: {len(messages)}",
        "",
        "---",
        "",
    ]
    body = [
        f"[{format_timestamp(message.create_time)}] {message.sender_display_name}: {message.text}"
        for message in messages
    ]
    path.write_text("\n".join(header + body) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, messages: list[ExportMessage]) -> None:
    lines = [json.dumps(asdict(message), ensure_ascii=False) for message in messages]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_manifest(
    out_dir: Path,
    account: AccountRef,
    exported_sessions: list[tuple[SessionRef, int, dict[str, str]]],
) -> Path:
    manifest_path = out_dir / "manifest.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "account": {
            "account_id": account.account_id,
            "account_dir": str(account.account_dir),
            "cleaned_wxid": account.cleaned_wxid,
        },
        "sessions": [
            {
                "username": session.username,
                "display_name": session.display_name,
                "is_chatroom": session.is_chatroom,
                "last_timestamp": session.last_timestamp,
                "message_count": count,
                "outputs": outputs,
            }
            for session, count, outputs in exported_sessions
        ],
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
