@echo off
cd /d "%~dp0"
where node >nul 2>&1
if errorlevel 1 (
  echo Node.js kell: https://nodejs.org/
  pause
  exit /b 1
)
if not exist node_modules (
  echo Csomagok telepítése…
  call npm install
)
echo.
echo Indítás — a többiek a LAN IP-det nyissák böngészőben.
echo.
node server.js
pause
