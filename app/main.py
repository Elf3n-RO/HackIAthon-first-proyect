from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agent import analizar_ingreso
from app.config import get_settings
from app.database import (
    buscar_poliza,
    guardar_alerta,
    init_db,
    listar_alertas,
    nueva_alerta_id,
)
from app.models import AlertaEmergencia, WebhookIngresoEmergencia
from app.notifications import enviar_notificaciones_paralelas

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Alerta Temprana — Ingresos a Emergencias",
    description=(
        "Sistema de alerta temprana para Ecuador. Webhook de ingreso a emergencias, "
        "agente IA de validación de póliza y preexistencias, notificación simultánea."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    alertas = await listar_alertas()
    settings = get_settings()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "alertas": alertas,
            "ia_configurada": settings.ia_configurada,
            "modelo": settings.openai_model,
        },
    )


@app.get("/api/health")
async def health():
    s = get_settings()
    return {
        "status": "ok",
        "pais": "Ecuador",
        "zona_horaria": "America/Guayaquil",
        "ia_configurada": s.ia_configurada,
        "modelo": s.openai_model if s.ia_configurada else "motor-local-ec-v1",
    }


@app.get("/api/alertas")
async def api_listar_alertas():
    return await listar_alertas()


@app.get("/api/polizas/{cedula}")
async def api_consultar_poliza(cedula: str):
    poliza = await buscar_poliza(cedula)
    if not poliza:
        raise HTTPException(404, detail="Póliza no encontrada para esta cédula")
    return poliza


@app.post("/api/webhook/ingreso-emergencia", response_model=AlertaEmergencia)
async def webhook_ingreso_emergencia(ingreso: WebhookIngresoEmergencia):
    """
    Webhook principal: el hospital lo invoca al registrar ingreso a emergencias.
    Dispara análisis IA y notificaciones paralelas a admisiones y gestor de casos.
    """
    ts = ingreso.timestamp_ingreso or datetime.now(timezone.utc)
    poliza = await buscar_poliza(ingreso.cedula, ingreso.numero_poliza)
    analisis = await analizar_ingreso(ingreso, poliza)

    nombre = poliza.titular if poliza else f"Paciente CI {ingreso.cedula}"

    alerta = AlertaEmergencia(
        id=nueva_alerta_id(),
        timestamp=ts,
        paciente_cedula=ingreso.cedula,
        paciente_nombre=nombre,
        hospital=ingreso.hospital_nombre,
        motivo=ingreso.motivo_consulta,
        triage=ingreso.triage_nivel,
        poliza=poliza,
        analisis=analisis,
        notificaciones_enviadas={},
    )

    alerta.notificaciones_enviadas = await enviar_notificaciones_paralelas(alerta)
    await guardar_alerta(alerta)
    return alerta


@app.post("/api/demo/simular-ingreso")
async def demo_simular(cedula: str = "1712345678"):
    """Simula un ingreso de emergencia para pruebas rápidas."""
    payload = WebhookIngresoEmergencia(
        cedula=cedula,
        hospital_codigo="HOSP-QUI-001",
        hospital_nombre="Hospital de Especialidades Guayaquil",
        motivo_consulta="Dolor torácico irradiado a brazo izquierdo",
        triage_nivel=2,
    )
    return await webhook_ingreso_emergencia(payload)
