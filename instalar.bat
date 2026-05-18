@echo off
chcp 65001 >nul
echo ============================================
echo  Alerta Temprana Emergencias - Instalacion
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado.
    echo Descargue Python 3.10+ desde https://www.python.org/downloads/
    echo Marque "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

python --version
echo.

if not exist "venv" (
    echo Creando entorno virtual...
    python -m venv venv
)

call venv\Scripts\activate.bat
echo Instalando dependencias (puede tardar unos minutos)...
python -m pip install --upgrade pip
pip install --default-timeout=120 -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR en la instalacion. Verifique conexion a Internet e intente de nuevo.
    pause
    exit /b 1
)

if not exist ".env" (
    copy .env.example .env
    echo Archivo .env creado. Configure OPENAI_API_KEY para IA en la nube.
)

echo.
echo Instalacion completada. Ejecute iniciar.bat para arrancar el sistema.
pause
