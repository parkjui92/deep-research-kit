#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' 'uv가 필요합니다. README의 설치 안내를 확인하세요.'
  read -r reply
  exit 1
fi
uv sync --frozen
printf '\n%s\n%s\n\n' '잠시 뒤 브라우저가 열립니다. 열리지 않으면 http://localhost:8501 을 직접 여세요.' '끝내려면 이 창에서 Ctrl+C를 누르세요.'
exec uv run streamlit run app.py --server.address 127.0.0.1
