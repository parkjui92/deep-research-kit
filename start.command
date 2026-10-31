#!/bin/sh
set -eu
cd "$(dirname "$0")"
# uv 찾기: PATH -> 흔한 설치 위치(설치 직후 PATH가 아직 반영되지 않은 창에서도 실행되게, #26).
UV=""
if command -v uv >/dev/null 2>&1; then
  UV="uv"
else
  for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -x "$candidate" ]; then
      UV="$candidate"
      break
    fi
  done
fi
if [ -z "$UV" ]; then
  printf '%s\n' 'uv를 찾지 못했습니다.' \
    ' 1. 터미널에서 curl -LsSf https://astral.sh/uv/install.sh | sh 를 실행합니다(또는 brew install uv).' \
    ' 2. 설치한 뒤 이 창을 닫고 start.command를 다시 실행합니다.' \
    '자세한 방법은 README.md의 「시작하기」를 보세요. 창을 닫으려면 Enter를 누르세요.'
  read -r reply
  exit 1
fi
# --frozen: uv.lock을 그대로 쓰고 다시 쓰지 않는다(#9).
"$UV" sync --frozen
printf '\n%s\n%s\n\n' '잠시 뒤 브라우저가 열립니다. 열리지 않으면 http://localhost:8501 을 직접 여세요.' '끝내려면 이 창에서 Ctrl+C를 누르세요.'
exec "$UV" run --frozen streamlit run app.py --server.address 127.0.0.1
