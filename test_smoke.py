"""Prueba rápida del flujo webhook + IA + notificaciones."""
import asyncio

from httpx import ASGITransport, AsyncClient

from app.database import init_db
from app.main import app


async def main() -> None:
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/health")
        print("health:", health.json())

        r = await client.post("/api/demo/simular-ingreso?cedula=1712345678")
        assert r.status_code == 200, r.text
        data = r.json()
        print("alerta:", data["id"])
        print("poliza_valida:", data["analisis"]["poliza_valida"])
        print("notificaciones:", data["notificaciones_enviadas"])
    print("OK - sistema operativo")


if __name__ == "__main__":
    asyncio.run(main())
