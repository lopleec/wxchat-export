from __future__ import annotations

import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

from .discovery import (
    DEFAULT_WECHAT_BINARY,
    current_platform_name,
    find_gdb_binary,
    find_lldb_binary,
    find_linux_runtime_base,
    find_runtime_text_base,
    resolve_running_wechat_binary,
)
from .elf import select_primary_linux_hook_candidate
from .macho import select_primary_hook_candidate


class KeyCaptureError(RuntimeError):
    pass


def _write_lldb_callback(script_path: Path) -> None:
    script_path.write_text(
        textwrap.dedent(
            """
            import lldb


            def capture_db_key(frame, bp_loc, _dict):
                process = frame.GetThread().GetProcess()
                x1 = frame.FindRegister("x1").GetValueAsUnsigned()
                x2 = frame.FindRegister("x2").GetValueAsUnsigned()
                if x1 and x2 == 32:
                    err = lldb.SBError()
                    raw = process.ReadMemory(x1, 32, err)
                    if err.Success():
                        print("WXCHAT_EXPORT_KEY=" + raw.hex())
                        process.Detach()
                        lldb.debugger.HandleCommand("quit")
                        return False
                return False
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _write_lldb_commands(commands_path: Path, callback_path: Path, pid: int, runtime_address: int) -> None:
    commands_path.write_text(
        textwrap.dedent(
            f"""
            command script import {callback_path}
            process attach --pid {pid}
            breakpoint set --address {hex(runtime_address)}
            breakpoint command add 1 -F {callback_path.stem}.capture_db_key
            process continue
            quit
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _capture_database_key_macos(
    pid: int,
    binary_path: Path,
    timeout: int,
) -> str:
    lldb_binary = find_lldb_binary()
    if not lldb_binary:
        raise KeyCaptureError("lldb not found in PATH")

    candidate = select_primary_hook_candidate(binary_path)
    text_base = find_runtime_text_base(pid, binary_path)
    runtime_address = text_base + candidate.file_offset

    with tempfile.TemporaryDirectory(prefix="wxchat-export-lldb-") as temp_dir:
        temp_path = Path(temp_dir)
        callback_path = temp_path / "wxchat_export_lldb.py"
        commands_path = temp_path / "commands.lldb"
        _write_lldb_callback(callback_path)
        _write_lldb_commands(commands_path, callback_path, pid, runtime_address)

        try:
            proc = subprocess.run(
                [lldb_binary, "-b", "-s", str(commands_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise KeyCaptureError("Timed out while waiting for the DB key breakpoint") from exc

    combined = "\n".join(filter(None, [proc.stdout, proc.stderr]))
    if "Not allowed to attach to process" in combined:
        raise KeyCaptureError(
            "LLDB is not allowed to attach to WeChat. On current macOS this can also mean AMFI "
            "blocked task_for_pid because the WeChat build is hardened and not debug-attachable. "
            "Check `wxchat-export doctor` for SIP / DevToolsSecurity diagnostics, or pass --db-key "
            "or use a different extraction path."
        )
    return _extract_key_from_debugger_output(combined, proc.returncode, "LLDB")


def _write_gdb_commands(commands_path: Path, pid: int, runtime_address: int) -> None:
    commands_path.write_text(
        textwrap.dedent(
            f"""
            set pagination off
            attach {pid}
            python
            import gdb

            class CaptureBreakpoint(gdb.Breakpoint):
                def stop(self):
                    rsi = int(gdb.parse_and_eval("$rsi"))
                    rdx = int(gdb.parse_and_eval("$rdx"))
                    if rsi and rdx == 32:
                        raw = gdb.selected_inferior().read_memory(rsi, 32).tobytes()
                        print("WXCHAT_EXPORT_KEY=" + raw.hex())
                        gdb.execute("detach")
                        gdb.execute("quit")
                    return False

            CaptureBreakpoint("*{hex(runtime_address)}")
            end
            continue
            quit
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _capture_database_key_linux(
    pid: int,
    binary_path: Path,
    timeout: int,
) -> str:
    gdb_binary = find_gdb_binary()
    if not gdb_binary:
        raise KeyCaptureError("gdb not found in PATH")

    effective_binary = resolve_running_wechat_binary(pid, binary_path)
    candidate = select_primary_linux_hook_candidate(effective_binary)
    base_addr = find_linux_runtime_base(pid, effective_binary)
    runtime_address = base_addr + candidate.target_va

    with tempfile.TemporaryDirectory(prefix="wxchat-export-gdb-") as temp_dir:
        temp_path = Path(temp_dir)
        commands_path = temp_path / "commands.gdb"
        _write_gdb_commands(commands_path, pid, runtime_address)
        try:
            proc = subprocess.run(
                [gdb_binary, "-q", "--nx", "-batch", "-x", str(commands_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise KeyCaptureError("Timed out while waiting for the DB key breakpoint") from exc

    combined = "\n".join(filter(None, [proc.stdout, proc.stderr]))
    lowered = combined.lower()
    if "operation not permitted" in lowered or ("ptrace" in lowered and "failed" in lowered):
        raise KeyCaptureError(
            "GDB is not allowed to attach to WeChat. On Linux this usually means ptrace is blocked "
            "by ptrace_scope, missing CAP_SYS_PTRACE, or insufficient privileges. "
            "Check `wxchat-export doctor` for Linux ptrace diagnostics, or pass --db-key."
        )
    return _extract_key_from_debugger_output(combined, proc.returncode, "GDB")


def _extract_key_from_debugger_output(output: str, returncode: int, debugger_name: str) -> str:
    match = re.search(r"WXCHAT_EXPORT_KEY=([0-9a-fA-F]{64})", output)
    if match:
        return match.group(1).lower()
    if returncode != 0:
        raise KeyCaptureError(output.strip() or f"{debugger_name} key capture failed")
    raise KeyCaptureError("Breakpoint never yielded a 32-byte database key")


def capture_database_key(
    pid: int,
    binary_path: Path = DEFAULT_WECHAT_BINARY,
    timeout: int = 30,
) -> str:
    system_name = current_platform_name()
    if system_name == "Darwin":
        return _capture_database_key_macos(pid, binary_path, timeout)
    if system_name == "Linux":
        return _capture_database_key_linux(pid, binary_path, timeout)
    raise KeyCaptureError(
        "Automatic DB key capture is not implemented on this platform yet. "
        "Use --db-key to continue."
    )
