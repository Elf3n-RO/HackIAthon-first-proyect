"""
Envío de notificaciones en paralelo a hospital y aseguradora.

Canales por destinatario (se ejecutan a la vez con asyncio.gather):
  1. Consola (siempre, para demo)
  2. Webhook HTTP (si URL configurada en .env)
  3. Correo SMTP (si servidor configurado en .env)
"""

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.config import get_settings
from app.models import AlertaEmergencia, NotificacionPayload


def _build_notifications(alerta: AlertaEmergencia) -> tuple[NotificacionPayload, NotificacionPayload]:
    """
    Construye dos mensajes personalizados:
    - hospital_admisiones: foco en triage y protocolos de admisión
    - gestor_casos: foco en póliza, preexistencias y autorización
    """
    a = alerta.analisis
    riesgo = a.riesgo_clinico_financiero.value.upper()
    prioridad = "urgente" if alerta.triage <= 2 else "alta" if alerta.triage == 3 else "normal"

    base_html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:600px">
      <h2 style="color:#c0392b">Alerta Temprana — Emergencias</h2>
      <p><strong>ID:</strong> {alerta.id}</p>
      <p><strong>Paciente:</strong> {alerta.paciente_nombre} (CI: {alerta.paciente_cedula})</p>
      <p><strong>Hospital:</strong> {alerta.hospital}</p>
      <p><strong>Motivo:</strong> {alerta.motivo}</p>
      <p><strong>Triage:</strong> {alerta.triage} | <strong>Riesgo:</strong> {riesgo}</p>
      <hr>
      <p>{a.resumen_ejecutivo}</p>
      <p><strong>Autorización sugerida:</strong> {a.autorizacion_sugerida}</p>
      <p><em>Modelo IA: {a.modelo_ia} ({a.tiempo_analisis_ms} ms)</em></p>
    </div>
    """

    hospital = NotificacionPayload(
        tipo_destino="hospital_admisiones",
        alerta_id=alerta.id,
        asunto=f"[EMERGENCIA T{alerta.triage}] {alerta.paciente_nombre} — {a.autorizacion_sugerida}",
        cuerpo_html=base_html + "<h3>Recomendaciones admisiones</h3><ul>"
        + "".join(f"<li>{r}</li>" for r in a.recomendaciones_admisiones)
        + "</ul>",
        cuerpo_texto="\n".join(
            [
                f"ALERTA {alerta.id}",
                f"Paciente: {alerta.paciente_nombre}",
                a.resumen_ejecutivo,
                "Recomendaciones:",
                *a.recomendaciones_admisiones,
            ]
        ),
        prioridad=prioridad,
    )

    gestor = NotificacionPayload(
        tipo_destino="gestor_casos",
        alerta_id=alerta.id,
        asunto=f"[CASO {alerta.id}] {alerta.paciente_nombre} — Póliza {a.estado_poliza.value}",
        cuerpo_html=base_html + "<h3>Recomendaciones gestor</h3><ul>"
        + "".join(f"<li>{r}</li>" for r in a.recomendaciones_gestor)
        + "</ul>"
        + (
            f"<p><strong>Preexistencias:</strong> {', '.join(a.preexistencias_relevantes) or 'Ninguna relevante'}</p>"
        ),
        cuerpo_texto="\n".join(
            [
                f"CASO {alerta.id}",
                f"Póliza válida: {a.poliza_valida}",
                a.resumen_ejecutivo,
                "Gestor:",
                *a.recomendaciones_gestor,
            ]
        ),
        prioridad=prioridad,
    )
    return hospital, gestor


async def _send_webhook(url: str, payload: NotificacionPayload) -> bool:
    """POST JSON al webhook del hospital o de la aseguradora."""
    if not url.strip():
        return False
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, json=payload.model_dump())
        return r.is_success


async def _send_email(to: str, payload: NotificacionPayload) -> bool:
    """Envía correo HTML/texto vía SMTP (Gmail, Outlook, etc.)."""
    settings = get_settings()
    if not settings.email_smtp_host.strip():
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = payload.asunto
    msg["From"] = settings.email_smtp_user
    msg["To"] = to
    msg.attach(MIMEText(payload.cuerpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(payload.cuerpo_html, "html", "utf-8"))

    def _smtp_send() -> None:
        with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port) as server:
            server.starttls()
            server.login(settings.email_smtp_user, settings.email_smtp_password)
            server.sendmail(settings.email_smtp_user, [to], msg.as_string())

    await asyncio.to_thread(_smtp_send)
    return True


def _safe_print(text: str) -> None:
    """Imprime en consola sin fallar en Windows con codificación cp1251."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _log_notification(payload: NotificacionPayload) -> bool:
    """Muestra la notificación en la terminal (modo demo siempre activo)."""
    _safe_print(f"\n{'='*60}")
    _safe_print(f"NOTIFICACION -> {payload.tipo_destino.upper()}")
    _safe_print(f"Asunto: {payload.asunto}")
    _safe_print(f"Prioridad: {payload.prioridad}")
    _safe_print(payload.cuerpo_texto[:500])
    _safe_print("=" * 60)
    return True


async def _dispatch_one(payload: NotificacionPayload, webhook_url: str, email_to: str) -> bool:
    """
    Despacha un mensaje por los 3 canales en paralelo.
    Retorna True si al menos un canal tuvo éxito.
    """
    tasks = [
        asyncio.to_thread(_log_notification, payload),
        _send_webhook(webhook_url, payload),
        _send_email(email_to, payload),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok = False
    for r in results:
        if r is True:
            ok = True
        elif isinstance(r, Exception):
            _safe_print(f"Error notificacion {payload.tipo_destino}: {r}")
    return ok


async def enviar_notificaciones_paralelas(alerta: AlertaEmergencia) -> dict[str, bool]:
    """
    Envía simultáneamente a admisiones hospitalarias y gestor de casos.
    asyncio.gather ejecuta ambos destinos al mismo tiempo (requisito del sistema).
    """
    settings = get_settings()
    hospital_payload, gestor_payload = _build_notifications(alerta)

    hospital_ok, gestor_ok = await asyncio.gather(
        _dispatch_one(
            hospital_payload,
            settings.webhook_hospital_admisiones,
            settings.email_hospital,
        ),
        _dispatch_one(
            gestor_payload,
            settings.webhook_gestor_casos,
            settings.email_gestor,
        ),
    )

    return {
        "hospital_admisiones": hospital_ok,
        "gestor_casos": gestor_ok,
    }
