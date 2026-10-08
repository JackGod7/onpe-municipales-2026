#!/bin/bash
# Gate local = CI. Correr antes de cada push.
set -e
cd "$(dirname "$0")"
uv sync --locked
uv run ruff check .
uv run pytest -q
if git ls-files | grep -E '^(data/|\.env$|.*\.db$|.*\.xlsx$)'; then echo "archivo prohibido en Git"; exit 1; fi
echo "gate OK"
