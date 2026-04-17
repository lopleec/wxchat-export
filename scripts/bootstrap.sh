#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

install_sqlcipher() {
  if command -v sqlcipher >/dev/null 2>&1; then
    return 0
  fi

  if command -v brew >/dev/null 2>&1; then
    echo "Installing sqlcipher via Homebrew..."
    brew install sqlcipher
    return 0
  fi

  cat >&2 <<'EOF'
sqlcipher is not installed and bootstrap could not install it automatically.

Install it with your system package manager, then rerun this script.
Examples:
  macOS (Homebrew): brew install sqlcipher
  Ubuntu/Debian:    sudo apt install sqlcipher
  Fedora:           sudo dnf install sqlcipher
  Arch Linux:       sudo pacman -S sqlcipher

You can also point the CLI at a custom binary with:
  export WXCHAT_EXPORT_SQLCIPHER=/path/to/sqlcipher
EOF
  exit 1
}

install_sqlcipher

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e "$ROOT_DIR"

echo
echo "Bootstrap complete."
echo "Activate with: source .venv/bin/activate"
