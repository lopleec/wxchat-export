from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from .models import AccountRef

ENV_WECHAT_BINARY = "WXCHAT_EXPORT_WECHAT_BINARY"
ENV_DATA_ROOT = "WXCHAT_EXPORT_DATA_ROOT"
ENV_SQLCIPHER = "WXCHAT_EXPORT_SQLCIPHER"
ENV_LLDB = "WXCHAT_EXPORT_LLDB"
ENV_GDB = "WXCHAT_EXPORT_GDB"

IGNORED_ACCOUNT_DIRS = {"all_users", "Backup", "WMPF"}


def current_platform_name() -> str:
    return platform.system()


def supports_automatic_key_capture(system_name: str | None = None) -> bool:
    return (system_name or current_platform_name()) in {"Darwin", "Linux"}


def _clean_candidate_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def _append_candidate(candidates: list[Path], value: str | Path | None) -> None:
    if not value:
        return
    path = _clean_candidate_path(value)
    if path not in candidates:
        candidates.append(path)


def wechat_binary_candidates(system_name: str | None = None) -> list[Path]:
    system_name = system_name or current_platform_name()
    candidates: list[Path] = []

    env_value = os.getenv(ENV_WECHAT_BINARY)
    if env_value:
        _append_candidate(candidates, env_value)
        return candidates

    if system_name == "Darwin":
        _append_candidate(candidates, "/Applications/WeChat.app/Contents/MacOS/WeChat")
        _append_candidate(candidates, "/Applications/WeChat.app/Contents/Frameworks/wechat.dylib")
    elif system_name == "Windows":
        program_files = os.getenv("ProgramFiles")
        program_files_x86 = os.getenv("ProgramFiles(x86)")
        if program_files:
            _append_candidate(candidates, Path(program_files) / "Tencent/WeChat/WeChat.exe")
        if program_files_x86:
            _append_candidate(candidates, Path(program_files_x86) / "Tencent/WeChat/WeChat.exe")
    elif system_name == "Linux":
        for name in ("wechat", "wechat-uos", "weixin"):
            binary = shutil.which(name)
            if binary:
                _append_candidate(candidates, binary)
        _append_candidate(candidates, "/usr/bin/wechat")
        _append_candidate(candidates, "/opt/wechat/wechat")

    return candidates


def data_root_candidates(system_name: str | None = None) -> list[Path]:
    system_name = system_name or current_platform_name()
    candidates: list[Path] = []

    env_value = os.getenv(ENV_DATA_ROOT)
    if env_value:
        _append_candidate(candidates, env_value)
        return candidates

    home = Path.home()

    if system_name == "Darwin":
        _append_candidate(
            candidates,
            home / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files",
        )
    elif system_name == "Windows":
        appdata = os.getenv("APPDATA")
        _append_candidate(candidates, home / "Documents/xwechat_files")
        _append_candidate(candidates, home / "Documents/WeChat Files")
        if appdata:
            appdata_path = Path(appdata)
            _append_candidate(candidates, appdata_path / "Tencent/xwechat")
            _append_candidate(candidates, appdata_path / "Tencent/xwechat_files")
    elif system_name == "Linux":
        _append_candidate(candidates, home / ".xwechat/xwechat_files")
        _append_candidate(candidates, home / ".xwechat")
        _append_candidate(candidates, home / ".local/share/xwechat_files")
        _append_candidate(candidates, home / ".var/app/com.tencent.WeChat/data/xwechat_files")

    return candidates


def _select_default_path(candidates: list[Path], fallback: str) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if candidates:
        return candidates[0]
    return Path(fallback)


def default_wechat_binary() -> Path:
    return _select_default_path(wechat_binary_candidates(), "WeChat")


def default_xwechat_root() -> Path:
    return _select_default_path(data_root_candidates(), "xwechat_files")


DEFAULT_WECHAT_BINARY = default_wechat_binary()
DEFAULT_XWECHAT_ROOT = default_xwechat_root()


def clean_wxid(account_id: str) -> str:
    parts = account_id.split("_")
    if account_id.startswith("wxid_") and len(parts) >= 3:
        return "_".join(parts[:2])
    return account_id


def discover_accounts(root: Path = DEFAULT_XWECHAT_ROOT) -> list[AccountRef]:
    if not root.exists():
        return []

    accounts: list[AccountRef] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        if child.name in IGNORED_ACCOUNT_DIRS:
            continue
        if not (child / "db_storage").is_dir():
            continue
        accounts.append(
            AccountRef(
                account_id=child.name,
                account_dir=child,
                cleaned_wxid=clean_wxid(child.name),
            )
        )
    return accounts


def resolve_account(account_id: str, root: Path = DEFAULT_XWECHAT_ROOT) -> AccountRef:
    for account in discover_accounts(root):
        if account.account_id == account_id:
            return account
    raise ValueError(f"Account not found: {account_id}")


def find_wechat_pid() -> int | None:
    system_name = current_platform_name()

    if system_name in {"Darwin", "Linux"}:
        for process_name in ("WeChat", "wechat", "weixin"):
            proc = subprocess.run(
                ["pgrep", "-x", process_name],
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                continue
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    return int(line)
        return None

    if system_name == "Windows":
        proc = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq WeChat.exe", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            parts = [part.strip().strip('"') for part in line.split(",")]
            if len(parts) >= 2 and parts[0].lower() == "wechat.exe" and parts[1].isdigit():
                return int(parts[1])
    return None


def find_sqlcipher_binary() -> str | None:
    env_value = os.getenv(ENV_SQLCIPHER)
    if env_value:
        return env_value
    return shutil.which("sqlcipher")


def find_lldb_binary() -> str | None:
    env_value = os.getenv(ENV_LLDB)
    if env_value:
        return env_value
    return shutil.which("lldb")


def find_gdb_binary() -> str | None:
    env_value = os.getenv(ENV_GDB)
    if env_value:
        return env_value
    return shutil.which("gdb")


def resolve_running_wechat_binary(pid: int, fallback: Path | None = None) -> Path:
    system_name = current_platform_name()
    if system_name == "Linux":
        proc_exe = Path(f"/proc/{pid}/exe")
        try:
            return proc_exe.resolve()
        except OSError:
            pass
    if fallback is not None:
        return fallback
    return DEFAULT_WECHAT_BINARY


def _run_text_command(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = "\n".join(filter(None, [proc.stdout, proc.stderr]))
    return proc.returncode, combined


def parse_vmmap_text_base(vmmap_output: str, binary_path: Path) -> int:
    current_path: str | None = None
    for line in vmmap_output.splitlines():
        if line.startswith("Path:"):
            current_path = line.split("Path:", 1)[1].strip()
            continue
        if current_path != str(binary_path):
            continue
        if not line.startswith("__TEXT"):
            continue
        match = re.search(r"__TEXT\s+([0-9a-fA-F]+)-", line)
        if match:
            return int(match.group(1), 16)
    raise RuntimeError(f"Unable to locate __TEXT mapping for {binary_path}")


def find_runtime_text_base(pid: int, binary_path: Path = DEFAULT_WECHAT_BINARY) -> int:
    if current_platform_name() != "Darwin":
        raise RuntimeError("Runtime text base discovery is currently only implemented on macOS")
    proc = subprocess.run(
        ["vmmap", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    )
    combined = "\n".join(filter(None, [proc.stdout, proc.stderr]))
    if proc.returncode != 0:
        raise RuntimeError(combined.strip() or "vmmap failed")
    return parse_vmmap_text_base(proc.stdout, binary_path)


def _read_recent_attach_denial(pid: int, minutes: int = 2) -> str | None:
    if current_platform_name() != "Darwin":
        return None
    log_binary = shutil.which("log")
    if not log_binary:
        return None
    returncode, combined = _run_text_command(
        [
            log_binary,
            "show",
            "--last",
            f"{minutes}m",
            "--style",
            "compact",
            "--predicate",
            'process == "kernel" OR process == "debugserver"',
        ]
    )
    if returncode != 0:
        return None

    for line in reversed(combined.splitlines()):
        if f"(pid: {pid})" not in line:
            continue
        if "macOSTaskPolicy:" not in line:
            continue
        detail = line.split("macOSTaskPolicy:", 1)[1].strip()
        detail = re.sub(r"\s+", " ", detail)
        if "doesn't have get-task-allow" in detail:
            return (
                "AMFI denied task_for_pid: target is release-signed / hardened and "
                "doesn't have get-task-allow; current debugserver is not a declared "
                "read-only debugger"
            )
        return f"AMFI denied task_for_pid: {detail}"
    return None


def _binary_uses_hardened_runtime(binary_path: Path) -> bool | None:
    if current_platform_name() != "Darwin":
        return None
    _returncode, combined = _run_text_command(["codesign", "-dv", "--verbose=4", str(binary_path)])
    if not combined:
        return None
    return "flags=0x10000(runtime)" in combined or "(runtime)" in combined


def _binary_has_get_task_allow(binary_path: Path) -> bool | None:
    if current_platform_name() != "Darwin":
        return None
    _returncode, combined = _run_text_command(["codesign", "-d", "--entitlements", ":-", str(binary_path)])
    if not combined:
        return None
    return (
        "com.apple.security.get-task-allow" in combined
        and "<true/>" in combined.split("com.apple.security.get-task-allow", 1)[1]
    )


def parse_devtoolssecurity_status(output: str) -> str:
    lower = output.lower()
    if "developer mode is currently enabled" in lower:
        return "enabled"
    if "developer mode is currently disabled" in lower:
        return "disabled"
    return "unknown"


def get_devtoolssecurity_status() -> tuple[str, str]:
    if current_platform_name() != "Darwin":
        return "unknown", "DevToolsSecurity is only available on macOS"
    returncode, combined = _run_text_command(["DevToolsSecurity", "-status"])
    if returncode != 0:
        return "unknown", combined.strip() or "DevToolsSecurity -status failed"
    return parse_devtoolssecurity_status(combined), combined.strip()


def parse_sip_status(output: str) -> str:
    lower = output.lower()
    if "system integrity protection status: enabled" in lower:
        return "enabled"
    if "system integrity protection status: disabled" in lower:
        return "disabled"
    return "unknown"


def get_sip_status() -> tuple[str, str]:
    if current_platform_name() != "Darwin":
        return "unknown", "SIP check is only available on macOS"
    returncode, combined = _run_text_command(["csrutil", "status"])
    if returncode != 0:
        return "unknown", combined.strip() or "csrutil status failed"
    return parse_sip_status(combined), combined.strip()


def parse_linux_ptrace_scope(output: str) -> int | None:
    value = output.strip()
    if not value.isdigit():
        return None
    return int(value)


def get_linux_ptrace_scope() -> tuple[int | None, str]:
    if current_platform_name() != "Linux":
        return None, "ptrace_scope check is only available on Linux"
    path = Path("/proc/sys/kernel/yama/ptrace_scope")
    if not path.exists():
        return None, "Yama ptrace_scope is not available on this kernel"
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return None, str(exc)
    value = parse_linux_ptrace_scope(raw)
    if value is None:
        return None, raw
    return value, raw


def parse_proc_maps_base(maps_output: str, binary_path: Path) -> int:
    candidates = {
        str(binary_path),
        str(binary_path.resolve()) if binary_path.exists() else str(binary_path),
        f"{binary_path} (deleted)",
    }
    binary_name = binary_path.name
    for line in maps_output.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 5:
            continue
        address_range, _perms, offset_hex, _dev, _inode, *rest = parts
        pathname = rest[0].strip() if rest else ""
        if int(offset_hex, 16) != 0:
            continue
        if pathname not in candidates and not pathname.endswith(f"/{binary_name}"):
            continue
        return int(address_range.split("-", 1)[0], 16)
    raise RuntimeError(f"Unable to locate base mapping for {binary_path}")


def find_linux_runtime_base(pid: int, binary_path: Path) -> int:
    if current_platform_name() != "Linux":
        raise RuntimeError("Linux runtime base discovery is only available on Linux")
    maps_path = Path(f"/proc/{pid}/maps")
    try:
        maps_output = maps_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
    return parse_proc_maps_base(maps_output, binary_path)


def is_user_in_developer_group() -> tuple[bool | None, str]:
    returncode, combined = _run_text_command(["id", "-Gn"])
    if returncode != 0:
        return None, combined.strip() or "id -Gn failed"
    groups = set(combined.split())
    return "_developer" in groups, combined.strip()


def get_attach_prerequisite_notes(binary_path: Path | None = None) -> list[str]:
    notes: list[str] = []

    if current_platform_name() == "Linux":
        ptrace_scope, _ = get_linux_ptrace_scope()
        if ptrace_scope is not None and ptrace_scope > 0:
            notes.append(f"ptrace_scope is {ptrace_scope}")
        return notes

    devtools_status, _ = get_devtoolssecurity_status()
    if devtools_status == "disabled":
        notes.append("DevToolsSecurity is disabled")

    in_developer_group, _ = is_user_in_developer_group()
    if in_developer_group is False:
        notes.append("current user is not in the _developer group")

    sip_status, _ = get_sip_status()
    if sip_status == "enabled":
        notes.append("SIP is enabled")

    if binary_path is not None:
        uses_runtime = _binary_uses_hardened_runtime(binary_path)
        has_get_task_allow = _binary_has_get_task_allow(binary_path)
        if uses_runtime and has_get_task_allow is False:
            notes.append("target uses hardened runtime and has no get-task-allow entitlement")

    return notes


def probe_lldb_attach(
    pid: int,
    binary_path: Path | None = None,
    timeout: int = 20,
) -> tuple[bool, str]:
    if current_platform_name() != "Darwin":
        return False, "Automatic LLDB attach probing is currently only implemented on macOS"
    lldb_binary = find_lldb_binary()
    if not lldb_binary:
        return False, "lldb not found in PATH"
    script = textwrap.dedent(
        f"""
        process attach --pid {pid}
        process detach
        quit
        """
    ).strip()
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(script)
        path = Path(handle.name)
    try:
        proc = subprocess.run(
            [lldb_binary, "-b", "-s", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "LLDB attach probe timed out"
    finally:
        path.unlink(missing_ok=True)

    combined = "\n".join(filter(None, [proc.stdout, proc.stderr]))
    if "Not allowed to attach to process" in combined:
        denial = _read_recent_attach_denial(pid)
        if denial:
            notes = get_attach_prerequisite_notes(binary_path)
            if "SIP is enabled" in notes:
                denial += (
                    "; SIP is enabled on this machine, which is a common reason this runtime "
                    "attach path still fails even after normal permission checks"
                )
            return False, denial
        if binary_path is not None:
            uses_runtime = _binary_uses_hardened_runtime(binary_path)
            has_get_task_allow = _binary_has_get_task_allow(binary_path)
            if uses_runtime and has_get_task_allow is False:
                notes = get_attach_prerequisite_notes(binary_path)
                suffix = ""
                if notes:
                    suffix = f" ({'; '.join(notes)})"
                return (
                    False,
                    "Likely blocked by AMFI: target uses hardened runtime and has no "
                    "get-task-allow entitlement, so LLDB attach is denied on this macOS build"
                    f"{suffix}",
                )
        notes = get_attach_prerequisite_notes(binary_path)
        if notes:
            return False, f"Not allowed to attach to process ({'; '.join(notes)})"
        return False, "Not allowed to attach to process"
    if proc.returncode != 0:
        return False, combined.strip() or "LLDB attach probe failed"
    return True, "ok"


def probe_gdb_attach(pid: int, timeout: int = 20) -> tuple[bool, str]:
    if current_platform_name() != "Linux":
        return False, "GDB attach probing is only available on Linux"
    gdb_binary = find_gdb_binary()
    if not gdb_binary:
        return False, "gdb not found in PATH"
    script = textwrap.dedent(
        f"""
        set pagination off
        attach {pid}
        detach
        quit
        """
    ).strip()
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(script)
        path = Path(handle.name)
    try:
        proc = subprocess.run(
            [gdb_binary, "-q", "--nx", "-batch", "-x", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "GDB attach probe timed out"
    finally:
        path.unlink(missing_ok=True)

    combined = "\n".join(filter(None, [proc.stdout, proc.stderr])).strip()
    lowered = combined.lower()
    if "operation not permitted" in lowered or ("ptrace" in lowered and "failed" in lowered):
        notes = get_attach_prerequisite_notes()
        if notes:
            return False, f"{combined or 'GDB attach failed'} ({'; '.join(notes)})"
        return False, combined or "GDB attach failed"
    if proc.returncode != 0:
        return False, combined or "GDB attach probe failed"
    return True, "ok"


def probe_debugger_attach(
    pid: int,
    binary_path: Path | None = None,
    timeout: int = 20,
) -> tuple[bool, str]:
    if current_platform_name() == "Darwin":
        return probe_lldb_attach(pid, binary_path=binary_path, timeout=timeout)
    if current_platform_name() == "Linux":
        return probe_gdb_attach(pid, timeout=timeout)
    return False, "Automatic debugger attach probing is not implemented on this platform"
