#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

find "$ROOT_DIR" -type d \( \
  -name '__pycache__' -o \
  -name '.pytest_cache' -o \
  -name '.mypy_cache' -o \
  -name '.ruff_cache' -o \
  -name '.cache' -o \
  -name '.ipynb_checkpoints' -o \
  -name 'htmlcov' -o \
  -name 'build' -o \
  -name 'dist' -o \
  -name 'out' -o \
  -name 'exports' -o \
  -name '*.egg-info' \
\) -print0 | while IFS= read -r -d '' path; do
  rm -rf "$path"
done

find "$ROOT_DIR" -type f \( \
  -name '*.pyc' -o \
  -name '*.pyo' -o \
  -name '.coverage' -o \
  -name 'coverage.xml' -o \
  -name '.DS_Store' -o \
  -name '*.log' -o \
  -name '*.tmp' -o \
  -name '*.swp' \
\) -print0 | while IFS= read -r -d '' path; do
  rm -f "$path"
done

echo "Removed caches, build artifacts, logs, and local export outputs."
