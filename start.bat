@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set "UV=uv"
where uv >nul 2>nul
if errorlevel 1 (
  py -m uv --version >nul 2>nul
  if errorlevel 1 (
    echo uv를 찾지 못했습니다.
    echo - 설치: PowerShell에서 winget install astral-sh.uv 실행 후 이 창을 닫고 다시 실행
    echo - pip로 설치했다면 Python의 Scripts 폴더가 PATH에 있는지 확인
    echo 자세한 방법은 README.md의 「시작하기」를 보세요.
    pause
    exit /b 1
  )
  set "UV=py -m uv"
)
%UV% sync --frozen
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo 잠시 뒤 브라우저가 열립니다. 열리지 않으면 http://localhost:8501 을 직접 여세요.
echo 끝내려면 이 창에서 Ctrl+C를 누르세요.
echo.
%UV% run streamlit run app.py --server.address 127.0.0.1
