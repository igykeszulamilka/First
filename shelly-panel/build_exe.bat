@echo off
REM Windows PC-n futtasd — innen készül a KAPCS.exe
cd /d "%~dp0"
where py >nul 2>&1 && set PY=py -3
if not defined PY (
  where python >nul 2>&1 && set PY=python
)
if not defined PY (
  echo Python kell a buildhez.
  pause
  exit /b 1
)

%PY% -m pip install --upgrade pip pyinstaller
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name KAPCS --add-data "index.html;." server.py

echo.
echo Kész: dist\KAPCS.exe
echo Másold át bárhova, majd indítsd — megnyitja a böngészőt.
pause
