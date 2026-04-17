from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .discovery import (
    DEFAULT_WECHAT_BINARY,
    DEFAULT_XWECHAT_ROOT,
    _binary_has_get_task_allow,
    _binary_uses_hardened_runtime,
    current_platform_name,
    data_root_candidates,
    discover_accounts,
    find_gdb_binary,
    find_lldb_binary,
    find_linux_runtime_base,
    get_linux_ptrace_scope,
    find_sqlcipher_binary,
    find_wechat_pid,
    get_devtoolssecurity_status,
    get_sip_status,
    is_user_in_developer_group,
    probe_debugger_attach,
    resolve_running_wechat_binary,
    resolve_account,
    supports_automatic_key_capture,
    wechat_binary_candidates,
)
from .elf import select_primary_linux_hook_candidate
from .exporters import write_manifest, write_session_exports
from .key_capture import KeyCaptureError, capture_database_key
from .macho import select_primary_hook_candidate
from .parser import WeChatRepository
from .sqlcipher import SQLCipherClient, SQLCipherError
from .text_utils import format_timestamp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wxchat-export")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--root")
    doctor_parser.add_argument("--wechat-binary")

    accounts_parser = subparsers.add_parser("accounts")
    accounts_parser.add_argument("--root")

    sessions_parser = subparsers.add_parser("sessions")
    sessions_parser.add_argument("--account", required=True)
    sessions_parser.add_argument("--root")
    sessions_parser.add_argument("--wechat-binary")
    sessions_parser.add_argument("--db-key", help=argparse.SUPPRESS)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--account", required=True)
    export_parser.add_argument("--session", required=True)
    export_parser.add_argument("--out", required=True)
    export_parser.add_argument("--root")
    export_parser.add_argument("--wechat-binary")
    export_parser.add_argument("--format", choices=("md", "jsonl", "both"), default="both")
    export_parser.add_argument("--db-key", help=argparse.SUPPRESS)

    return parser


def _resolve_sqlcipher() -> SQLCipherClient:
    binary = find_sqlcipher_binary()
    if not binary:
        raise RuntimeError("sqlcipher is not installed. Run ./scripts/bootstrap.sh first.")
    return SQLCipherClient(binary=binary)


def _resolve_root(root: str | None) -> Path:
    if root:
        return Path(root).expanduser().resolve()
    return DEFAULT_XWECHAT_ROOT


def _resolve_wechat_binary(wechat_binary: str | None) -> Path:
    if wechat_binary:
        return Path(wechat_binary).expanduser().resolve()
    return DEFAULT_WECHAT_BINARY


def _resolve_key(db_key: str | None, wechat_binary: Path) -> str:
    if db_key:
        value = db_key.strip().lower()
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise RuntimeError("--db-key must be a 64-character hex string")
        return value

    if not supports_automatic_key_capture():
        raise RuntimeError(
            "Automatic DB key capture is currently only implemented on macOS and Linux. "
            "On this platform, pass --db-key and, if needed, override --root / --wechat-binary."
        )

    pid = find_wechat_pid()
    if pid is None:
        raise RuntimeError("WeChat is not running. Start WeChat or provide --db-key.")
    return capture_database_key(pid, wechat_binary)


def run_doctor(root: str | None, wechat_binary: str | None) -> int:
    ok = True
    root_path = _resolve_root(root)
    binary_path = _resolve_wechat_binary(wechat_binary)
    platform_name = current_platform_name()

    if supports_automatic_key_capture():
        print(f"[ok] Platform: {platform_name}")
    else:
        print(
            f"[warn] Platform: {platform_name} "
            "(automatic key capture is not implemented; parsing/export still work with --db-key)"
        )

    if binary_path.exists():
        print(f"[ok] WeChat binary: {binary_path}")
    else:
        if platform_name == "Darwin":
            ok = False
            print(f"[error] WeChat binary missing: {binary_path}")
        else:
            print(f"[warn] WeChat binary missing: {binary_path}")

    if root_path.exists():
        print(f"[ok] WeChat data root: {root_path}")
    else:
        ok = False
        print(f"[error] WeChat data root missing: {root_path}")
        candidates = [str(path) for path in data_root_candidates()[:5]]
        if candidates:
            print(f"[warn] Data root candidates tried: {', '.join(candidates)}")

    accounts = discover_accounts(root_path)
    if accounts:
        print(f"[ok] Accounts discovered: {len(accounts)}")
    else:
        ok = False
        print("[error] No account directories with db_storage were found")

    sqlcipher_binary = find_sqlcipher_binary()
    if sqlcipher_binary:
        print(f"[ok] sqlcipher: {sqlcipher_binary}")
    else:
        ok = False
        print("[error] sqlcipher not found in PATH")

    if platform_name == "Darwin":
        lldb_binary = find_lldb_binary()
        if lldb_binary:
            print(f"[ok] lldb: {lldb_binary}")
        else:
            ok = False
            print("[error] lldb not found in PATH")

        devtools_status, devtools_message = get_devtoolssecurity_status()
        if devtools_status == "enabled":
            print("[ok] DevToolsSecurity: enabled")
        elif devtools_status == "disabled":
            ok = False
            print("[error] DevToolsSecurity: disabled")
        else:
            print(f"[warn] DevToolsSecurity: {devtools_message}")

        in_developer_group, developer_group_message = is_user_in_developer_group()
        if in_developer_group is True:
            print("[ok] _developer group: current user is in _developer")
        elif in_developer_group is False:
            print("[warn] _developer group: current user is not in _developer")
        else:
            print(f"[warn] _developer group: {developer_group_message}")

        sip_status, sip_message = get_sip_status()
        if sip_status == "disabled":
            print("[ok] SIP: disabled")
        elif sip_status == "enabled":
            print("[warn] SIP: enabled")
        else:
            print(f"[warn] SIP: {sip_message}")

        if binary_path.exists():
            uses_runtime = _binary_uses_hardened_runtime(binary_path)
            has_get_task_allow = _binary_has_get_task_allow(binary_path)
            if uses_runtime is True:
                print("[ok] WeChat hardened runtime: enabled")
            elif uses_runtime is False:
                print("[warn] WeChat hardened runtime: not detected")
            else:
                print("[warn] WeChat hardened runtime: unknown")

            if has_get_task_allow is True:
                print("[ok] WeChat get-task-allow: present")
            elif has_get_task_allow is False:
                print("[warn] WeChat get-task-allow: absent")
            else:
                print("[warn] WeChat get-task-allow: unknown")
    elif platform_name == "Linux":
        gdb_binary = find_gdb_binary()
        if gdb_binary:
            print(f"[ok] gdb: {gdb_binary}")
        else:
            ok = False
            print("[error] gdb not found in PATH")

        ptrace_scope, ptrace_message = get_linux_ptrace_scope()
        if ptrace_scope is None:
            print(f"[warn] ptrace_scope: {ptrace_message}")
        elif ptrace_scope == 0:
            print("[ok] ptrace_scope: 0")
        elif ptrace_scope in {1, 2}:
            print(f"[warn] ptrace_scope: {ptrace_scope}")
        else:
            ok = False
            print(f"[error] ptrace_scope: {ptrace_scope}")
    else:
        candidates = [str(path) for path in wechat_binary_candidates()[:5]]
        if candidates:
            print(f"[warn] WeChat binary candidates: {', '.join(candidates)}")

    pid = find_wechat_pid()
    if pid is None:
        if supports_automatic_key_capture():
            ok = False
            print("[error] WeChat process not running")
        else:
            print("[warn] WeChat process not running")
    else:
        print(f"[ok] WeChat PID: {pid}")
        if platform_name == "Darwin":
            try:
                candidate = select_primary_hook_candidate(binary_path)
                print(f"[ok] Hook candidate VM address: {hex(candidate.vmaddr)}")
            except Exception as exc:
                ok = False
                print(f"[error] Hook scanner failed: {exc}")
            attach_ok, attach_message = probe_debugger_attach(pid, binary_path)
            if attach_ok:
                print("[ok] LLDB attach permission: ok")
            else:
                ok = False
                print(f"[error] LLDB attach permission: {attach_message}")
        elif platform_name == "Linux":
            try:
                effective_binary = resolve_running_wechat_binary(pid, binary_path)
                candidate = select_primary_linux_hook_candidate(effective_binary)
                runtime_base = find_linux_runtime_base(pid, effective_binary)
                print(f"[ok] WeChat binary (runtime): {effective_binary}")
                print(f"[ok] Hook candidate VA: {hex(candidate.target_va)}")
                print(f"[ok] Hook candidate runtime address: {hex(runtime_base + candidate.target_va)}")
            except Exception as exc:
                ok = False
                print(f"[error] Hook scanner failed: {exc}")
            attach_ok, attach_message = probe_debugger_attach(pid, binary_path)
            if attach_ok:
                print("[ok] GDB attach permission: ok")
            else:
                ok = False
                print(f"[error] GDB attach permission: {attach_message}")
        else:
            print("[warn] Hook scanner: skipped on this platform")
            print("[warn] Debugger attach permission: skipped on this platform")

    return 0 if ok else 1


def run_accounts(root: str | None) -> int:
    accounts = discover_accounts(_resolve_root(root))
    if not accounts:
        print("No accounts found.")
        return 1
    for account in accounts:
        print(f"{account.account_id}\t{account.cleaned_wxid}\t{account.account_dir}")
    return 0


def run_sessions(account_id: str, db_key: str | None, root: str | None, wechat_binary: str | None) -> int:
    root_path = _resolve_root(root)
    binary_path = _resolve_wechat_binary(wechat_binary)
    account = resolve_account(account_id, root_path)
    key_hex = _resolve_key(db_key, binary_path)
    repo = WeChatRepository(account, key_hex, _resolve_sqlcipher())
    repo.probe()
    for session in repo.list_sessions():
        print(
            "\t".join(
                [
                    session.username,
                    session.display_name,
                    "chatroom" if session.is_chatroom else "direct",
                    format_timestamp(session.last_timestamp),
                ]
            )
        )
    return 0


def run_export(
    account_id: str,
    session_username: str,
    out_dir: str,
    export_format: str,
    db_key: str | None,
    root: str | None,
    wechat_binary: str | None,
) -> int:
    root_path = _resolve_root(root)
    binary_path = _resolve_wechat_binary(wechat_binary)
    account = resolve_account(account_id, root_path)
    key_hex = _resolve_key(db_key, binary_path)
    repo = WeChatRepository(account, key_hex, _resolve_sqlcipher())
    repo.probe()

    sessions = repo.list_sessions()
    if session_username != "all":
        sessions = [session for session in sessions if session.username == session_username]
        if not sessions:
            raise RuntimeError(f"Session not found: {session_username}")

    out_path = Path(out_dir).expanduser().resolve()
    exported: list[tuple] = []
    for session in sessions:
        messages = repo.load_messages(session)
        outputs = write_session_exports(out_path, account, session, messages, export_format)
        exported.append((session, len(messages), outputs))
        print(
            f"Exported {session.display_name} ({session.username}) -> {len(messages)} messages"
        )

    manifest_path = write_manifest(out_path, account, exported)
    print(f"Manifest written to {manifest_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return run_doctor(args.root, args.wechat_binary)
        if args.command == "accounts":
            return run_accounts(args.root)
        if args.command == "sessions":
            return run_sessions(args.account, args.db_key, args.root, args.wechat_binary)
        if args.command == "export":
            return run_export(
                args.account,
                args.session,
                args.out,
                args.format,
                args.db_key,
                args.root,
                args.wechat_binary,
            )
    except (RuntimeError, KeyCaptureError, SQLCipherError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
