@echo off
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo uv is required. See README.md for setup instructions.
  pause
  exit /b 1
)
uv sync --frozen
if errorlevel 1 (
  pause
  exit /b 1
)
uv run streamlit run app.py --server.address 127.0.0.1
