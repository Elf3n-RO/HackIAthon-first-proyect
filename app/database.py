"""
Capa de persistencia SQLite (async con aiosqlite).

Tablas:
  - polizas: asegurados demo con preexistencias (datos de prueba Ecuador)
  - alertas: historial de cada ingreso procesado por el webhook
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from app.models import AlertaEmergencia, EstadoPoliza, PolizaInfo, Preexistencia

# Base de datos en carpeta data/ (se crea automáticamente)
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "alertas.db"


async def init_db() -> None:
    """Crea tablas si no existen y carga pólizas demo la primera vez."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alertas (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                payload TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS polizas (
                cedula TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        await db.commit()
        await _seed_polizas(db)


async def _seed_polizas(db: aiosqlite.Connection) -> None:
    """Inserta pacientes de demostración solo si la tabla está vacía."""
    cursor = await db.execute("SELECT COUNT(*) FROM polizas")
    row = await cursor.fetchone()
    if row and row[0] > 0:
        return

    # Datos ficticios de aseguradoras ecuatorianas para pruebas del hackathon
    demo: list[dict] = [
        {
            "cedula": "1712345678",
            "poliza": {
                "numero": "POL-EC-2024-001234",
                "aseguradora": "Seguros del Pacífico S.A.",
                "estado": "vigente",
                "titular": "María Fernanda Pérez Gómez",
                "cedula": "1712345678",
                "vigencia_desde": "2024-01-15",
                "vigencia_hasta": "2026-01-14",
                "plan": "Platinum Salud Integral",
                "copago_porcentaje": 10.0,
                "tope_anual_usd": 150000.0,
                "preexistencias": [
                    {
                        "codigo": "E11",
                        "descripcion": "Diabetes mellitus tipo 2",
                        "fecha_diagnostico": "2019-06-12",
                        "cubierta": True,
                        "observaciones": "Controlada con metformina",
                    },
                    {
                        "codigo": "I10",
                        "descripcion": "Hipertensión esencial",
                        "fecha_diagnostico": "2018-03-20",
                        "cubierta": True,
                    },
                ],
            },
        },
        {
            "cedula": "1723456789",
            "poliza": {
                "numero": "POL-EC-2023-009876",
                "aseguradora": "Seguros Equinoccial",
                "estado": "vigente",
                "titular": "Carlos Andrés Mendoza Vera",
                "cedula": "1723456789",
                "vigencia_desde": "2023-08-01",
                "vigencia_hasta": "2025-07-31",
                "plan": "Salud Plus Familiar",
                "copago_porcentaje": 20.0,
                "tope_anual_usd": 80000.0,
                "preexistencias": [
                    {
                        "codigo": "J45",
                        "descripcion": "Asma bronquial",
                        "fecha_diagnostico": "2015-11-03",
                        "cubierta": True,
                    }
                ],
            },
        },
        {
            "cedula": "1709876543",
            "poliza": {
                "numero": "POL-EC-2022-004455",
                "aseguradora": "Latina Seguros C.A.",
                "estado": "vencida",
                "titular": "Ana Lucía Torres Castro",
                "cedula": "1709876543",
                "vigencia_desde": "2022-05-10",
                "vigencia_hasta": "2024-05-09",
                "plan": "Básico Ambulatorio",
                "copago_porcentaje": 30.0,
                "tope_anual_usd": 25000.0,
                "preexistencias": [
                    {
                        "codigo": "M54",
                        "descripcion": "Lumbalgia crónica",
                        "fecha_diagnostico": "2020-02-14",
                        "cubierta": False,
                        "observaciones": "Excluida del plan básico",
                    }
                ],
            },
        },
        {
            "cedula": "1756789012",
            "poliza": {
                "numero": "POL-EC-2024-007890",
                "aseguradora": "BMI Ecuador",
                "estado": "suspendida",
                "titular": "Roberto José Salinas Ortiz",
                "cedula": "1756789012",
                "vigencia_desde": "2024-03-01",
                "vigencia_hasta": "2026-02-28",
                "plan": "Ejecutivo Internacional",
                "copago_porcentaje": 5.0,
                "tope_anual_usd": 250000.0,
                "preexistencias": [
                    {
                        "codigo": "I25",
                        "descripcion": "Cardiopatía isquémica crónica",
                        "fecha_diagnostico": "2021-09-08",
                        "cubierta": True,
                        "observaciones": "Stent previo — requiere autorización cardiológica",
                    }
                ],
            },
        },
    ]

    for item in demo:
        await db.execute(
            "INSERT INTO polizas (cedula, data) VALUES (?, ?)",
            (item["cedula"], json.dumps(item["poliza"], ensure_ascii=False)),
        )
    await db.commit()


async def buscar_poliza(cedula: str, numero_poliza: str | None = None) -> PolizaInfo | None:
    """Busca póliza por cédula; opcionalmente valida que coincida el número de póliza."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT data FROM polizas WHERE cedula = ?", (cedula.strip(),))
        row = await cursor.fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        if numero_poliza and data.get("numero") != numero_poliza:
            return None
        preexistencias = [Preexistencia(**p) for p in data.get("preexistencias", [])]
        return PolizaInfo(
            numero=data["numero"],
            aseguradora=data["aseguradora"],
            estado=EstadoPoliza(data["estado"]),
            titular=data["titular"],
            cedula=data["cedula"],
            vigencia_desde=data["vigencia_desde"],
            vigencia_hasta=data["vigencia_hasta"],
            plan=data["plan"],
            copago_porcentaje=data["copago_porcentaje"],
            tope_anual_usd=data["tope_anual_usd"],
            preexistencias=preexistencias,
        )


async def guardar_alerta(alerta: AlertaEmergencia) -> None:
    """Persiste la alerta completa como JSON para el panel y auditoría."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO alertas (id, timestamp, payload) VALUES (?, ?, ?)",
            (
                alerta.id,
                alerta.timestamp.isoformat(),
                alerta.model_dump_json(),
            ),
        )
        await db.commit()


async def listar_alertas(limit: int = 50) -> list[AlertaEmergencia]:
    """Devuelve las alertas más recientes para el dashboard."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT payload FROM alertas ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    result: list[AlertaEmergencia] = []
    for (payload,) in rows:
        result.append(AlertaEmergencia.model_validate_json(payload))
    return result


def nueva_alerta_id() -> str:
    """Genera ID único tipo ALT-20260518-AB12CD34."""
    return f"ALT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
