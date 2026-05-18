@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Ejecute primero instalar.bat
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
echo.
echo Servidor: http://localhost:8000
echo Documentacion API: http://localhost:8000/docs
echo.
python run.py
pause
