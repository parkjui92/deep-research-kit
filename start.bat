@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

rem uv 찾기: PATH -> 흔한 설치 위치 -> py -m uv.
rem 방금 winget으로 설치하면 탐색기가 새 PATH를 모르므로 설치 위치를 직접 본다(#26).
set "UV="
where uv >nul 2>nul && set "UV=uv"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set UV="%USERPROFILE%\.local\bin\uv.exe"
if not defined UV if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set UV="%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
if not defined UV for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*") do if exist "%%D\uv.exe" set UV="%%D\uv.exe"
if not defined UV if exist "%USERPROFILE%\.cargo\bin\uv.exe" set UV="%USERPROFILE%\.cargo\bin\uv.exe"
if not defined UV py -m uv --version >nul 2>nul && set "UV=py -m uv"
if not defined UV goto no_uv

rem --frozen: uv.lock을 그대로 쓰고 다시 쓰지 않는다(#9).
%UV% sync --frozen
if errorlevel 1 goto failed
echo.
echo 잠시 뒤 브라우저가 열립니다. 열리지 않으면 http://localhost:8501 을 직접 여세요.
echo 끝내려면 이 창에서 Ctrl+C를 누르세요.
echo.
%UV% run --frozen streamlit run app.py --server.address 127.0.0.1
goto :eof

:no_uv
echo uv를 찾지 못했습니다.
echo  1. PowerShell이나 명령 프롬프트에서 winget install astral-sh.uv 를 실행합니다.
echo  2. 설치한 뒤 이 창을 닫고 start.bat을 다시 실행합니다.
echo  3. 그래도 같은 안내가 나오면 로그아웃 후 다시 로그인하거나 컴퓨터를 다시 시작합니다.
echo     방금 설치했는데도 이 안내가 나오면 3번이 필요한 경우입니다.
echo pip로 uv를 설치했다면 Python의 Scripts 폴더가 PATH에 있는지 확인하세요.
echo 자세한 방법은 README.md의 「시작하기」를 보세요.
pause
exit /b 1

:failed
echo.
echo 설치가 끝나지 않았습니다. 위 오류 문구를 README.md 「시작하기」의 '설치가 막힐 때'와 견주어 보세요.
pause
exit /b 1
