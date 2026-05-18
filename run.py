"""
Punto de entrada del servidor.

Uso:
    python run.py
    o ejecutar iniciar.bat / iniciar.sh

Lee HOST y PORT desde el archivo .env (ver app/config.py).
"""

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    # Carga configuración una vez al arrancar
    s = get_settings()
    # uvicorn sirve la aplicación FastAPI definida en app.main:app
    uvicorn.run(
        "app.main:app",
        host=s.host,
        port=s.port,
        reload=False,
    )
