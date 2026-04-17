#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT_DIR / ".venv"


def _run(argv: list[str]) -> None:
    subprocess.run(argv, check=True)


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts/python.exe"
    return VENV_DIR / "bin/python"


def _activation_hint() -> str:
    if os.name == "nt":
        return r".venv\Scripts\activate"
    return "source .venv/bin/activate"


def _locate_sqlcipher() -> str | None:
    env_value = os.getenv("WXCHAT_EXPORT_SQLCIPHER")
    if env_value:
        return env_value
    return shutil.which("sqlcipher")


def main() -> int:
    sqlcipher_binary = _locate_sqlcipher()
    if sqlcipher_binary:
        print(f"[ok] sqlcipher: {sqlcipher_binary}")
    else:
        print(
            "[warn] sqlcipher not found. Install it with your system package manager "
            "or set WXCHAT_EXPORT_SQLCIPHER before running export commands.",
            file=sys.stderr,
        )

    if not VENV_DIR.exists():
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)

    python_binary = _venv_python()
    _run([str(python_binary), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(python_binary), "-m", "pip", "install", "-e", str(ROOT_DIR)])

    print()
    print("Bootstrap complete.")
    print(f"Activate with: {_activation_hint()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
