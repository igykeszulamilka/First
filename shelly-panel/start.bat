@echo off
cd /d "%~dp0"
where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python server.py
  goto :eof
)
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 server.py
  goto :eof
)
echo Python nincs telepítve.
echo Telepítsd: https://www.python.org/downloads/
echo (pipálás közben pipáld be: "Add python.exe to PATH")
echo.
echo Vagy Windows-on építs .exe-t: build_exe.bat
pause
