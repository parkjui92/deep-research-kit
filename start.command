#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' 'uv가 필요합니다. README의 설치 안내를 확인하세요.'
  read -r reply
  exit 1
fi
uv sync --frozen
exec uv run streamlit run app.py --server.address 127.0.0.1
