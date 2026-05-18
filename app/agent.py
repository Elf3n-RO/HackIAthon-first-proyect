"""
Agente de inteligencia artificial para validación de ingresos a emergencias.

Flujo:
  1. Si hay API configurada (.env) → llama a OpenAI / Ollama / Groq (LLM).
  2. Si falla o no hay API → motor local con reglas y palabras clave en español.

El LLM recibe contexto ecuatoriano (SCVS, IESS) y devuelve JSON estructurado.
"""

import json
import logging
import time
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings
from app.models import (
    AnalisisIA,
    EstadoPoliza,
    NivelRiesgo,
    PolizaInfo,
    WebhookIngresoEmergencia,
)

logger = logging.getLogger(__name__)

# Instrucciones del sistema: define el rol del modelo y el marco legal en Ecuador
SYSTEM_PROMPT = """Eres un agente de inteligencia artificial especializado en admisiones hospitalarias
y gestión de seguros de salud en Ecuador. Tu rol es analizar ingresos a emergencias de asegurados.

Contexto regulatorio Ecuador:
- Superintendencia de Compañías, Valores y Seguros (SCVS) regula pólizas privadas.
- IESS cubre afiliación obligatoria; las pólizas privadas son complementarias.
- Debes considerar preexistencias declaradas, exclusiones y vigencia de póliza.
- Responde SIEMPRE en español ecuatoriano, profesional y conciso.
- Horario de referencia: zona horaria America/Guayaquil (UTC-5).

Debes evaluar: validez de póliza, impacto de preexistencias vs motivo de consulta,
riesgo clínico-financiero, y dar recomendaciones separadas para admisiones hospitalarias
y para el gestor de casos de la aseguradora."""

# Plantilla del mensaje del usuario: incluye datos del ingreso y JSON de la póliza
USER_PROMPT_TEMPLATE = """INGRESO A EMERGENCIAS — ANÁLISIS INMEDIATO

Paciente cédula: {cedula}
Hospital: {hospital} ({codigo})
Motivo consulta: {motivo}
Triage (1=crítico): {triage}

DATOS DE PÓLIZA:
{poliza_json}

Responde ÚNICAMENTE con un JSON válido (sin markdown) con esta estructura exacta:
{{
  "resumen_ejecutivo": "string (máx 300 caracteres)",
  "poliza_valida": boolean,
  "estado_poliza": "vigente|vencida|suspendida|no_encontrada",
  "riesgo_clinico_financiero": "bajo|medio|alto|critico",
  "preexistencias_relevantes": ["string"],
  "exclusiones_detectadas": ["string"],
  "recomendaciones_admisiones": ["string"],
  "recomendaciones_gestor": ["string"],
  "autorizacion_sugerida": "aprobar|autorizacion_previa|negar|revision_manual",
  "confianza": 0.0-1.0
}}"""


async def analizar_ingreso(
    ingreso: WebhookIngresoEmergencia,
    poliza: PolizaInfo | None,
) -> AnalisisIA:
    """
    Punto de entrada del agente IA.
    Intenta LLM si está configurado; si no, usa motor local.
    """
    inicio = time.perf_counter()
    settings = get_settings()

    if settings.ia_configurada:
        try:
            return await _analizar_con_llm(ingreso, poliza, inicio)
        except Exception as exc:
            # Registra el error en consola para depurar (clave inválida, Ollama apagado, etc.)
            logger.warning("Fallo LLM (%s). Usando motor local.", exc)

    return _analizar_local_ia(ingreso, poliza, inicio)


async def verificar_conexion_ia() -> dict[str, Any]:
    """
    Prueba rápida de conectividad con el proveedor de IA.
    Usado por GET /api/ia/verificar
    """
    settings = get_settings()
    if not settings.ia_configurada:
        return {
            "ok": False,
            "mensaje": "IA no configurada. Edite .env con OPENAI_API_KEY o Ollama.",
            "ia_configurada": False,
        }

    client = AsyncOpenAI(
        api_key=settings.openai_api_key or "ollama",
        base_url=settings.openai_base_url,
    )
    inicio = time.perf_counter()
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": 'Responde solo: {"ok": true}'}],
            max_tokens=20,
        )
        texto = (response.choices[0].message.content or "").strip()
        ms = int((time.perf_counter() - inicio) * 1000)
        return {
            "ok": True,
            "mensaje": "Conexión exitosa con el modelo de IA",
            "ia_configurada": True,
            "modelo": settings.openai_model,
            "base_url": settings.openai_base_url,
            "respuesta_prueba": texto[:200],
            "latencia_ms": ms,
        }
    except Exception as exc:
        return {
            "ok": False,
            "mensaje": str(exc),
            "ia_configurada": True,
            "modelo": settings.openai_model,
            "base_url": settings.openai_base_url,
        }


async def _analizar_con_llm(
    ingreso: WebhookIngresoEmergencia,
    poliza: PolizaInfo | None,
    inicio: float,
) -> AnalisisIA:
    """Llama al modelo de lenguaje vía API compatible con OpenAI."""
    settings = get_settings()
    client = AsyncOpenAI(
        api_key=settings.openai_api_key or "ollama",
        base_url=settings.openai_base_url,
    )

    # Serializa la póliza para incluirla en el prompt
    if poliza:
        poliza_data: dict[str, Any] = poliza.model_dump(mode="json")
    else:
        poliza_data = {"estado": "no_encontrada", "mensaje": "Sin póliza registrada para esta cédula"}

    user_msg = USER_PROMPT_TEMPLATE.format(
        cedula=ingreso.cedula,
        hospital=ingreso.hospital_nombre,
        codigo=ingreso.hospital_codigo,
        motivo=ingreso.motivo_consulta,
        triage=ingreso.triage_nivel,
        poliza_json=json.dumps(poliza_data, ensure_ascii=False, indent=2),
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    # OpenAI soporta response_format json_object; Ollama a veces no → intentamos ambos
    raw = await _completar_json(client, settings.openai_model, messages)
    data = json.loads(raw)
    elapsed = int((time.perf_counter() - inicio) * 1000)

    return _mapear_respuesta_llm(data, settings.openai_model, elapsed)


async def _completar_json(client: AsyncOpenAI, model: str, messages: list[dict]) -> str:
    """Obtiene respuesta JSON del LLM; reintenta sin response_format si el proveedor no lo soporta."""
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )

    content = response.choices[0].message.content or "{}"
    # Algunos modelos envuelven JSON en ```json ... ```
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return content


def _mapear_respuesta_llm(data: dict, modelo: str, elapsed: int) -> AnalisisIA:
    """Convierte el JSON del LLM al modelo AnalisisIA validado por Pydantic."""
    estado_raw = data.get("estado_poliza", "no_encontrada")
    riesgo_raw = data.get("riesgo_clinico_financiero", "medio")
    try:
        estado = EstadoPoliza(estado_raw)
    except ValueError:
        estado = EstadoPoliza.NO_ENCONTRADA
    try:
        riesgo = NivelRiesgo(riesgo_raw)
    except ValueError:
        riesgo = NivelRiesgo.MEDIO

    return AnalisisIA(
        resumen_ejecutivo=data.get("resumen_ejecutivo", "Análisis completado."),
        poliza_valida=bool(data.get("poliza_valida", False)),
        estado_poliza=estado,
        riesgo_clinico_financiero=riesgo,
        preexistencias_relevantes=data.get("preexistencias_relevantes", []),
        exclusiones_detectadas=data.get("exclusiones_detectadas", []),
        recomendaciones_admisiones=data.get("recomendaciones_admisiones", []),
        recomendaciones_gestor=data.get("recomendaciones_gestor", []),
        autorizacion_sugerida=data.get("autorizacion_sugerida", "revision_manual"),
        confianza=float(data.get("confianza", 0.85)),
        tiempo_analisis_ms=elapsed,
        modelo_ia=modelo,
    )


def _analizar_local_ia(
    ingreso: WebhookIngresoEmergencia,
    poliza: PolizaInfo | None,
    inicio: float,
) -> AnalisisIA:
    """
    Motor de inferencia local (sin API externa).
    Usa reglas: estado de póliza, triage, y coincidencia léxica motivo ↔ preexistencias.
    """

    motivo = ingreso.motivo_consulta.lower()
    preexistencias_rel: list[str] = []
    exclusiones: list[str] = []
    rec_adm: list[str] = []
    rec_gestor: list[str] = []

    # Palabras clave en español para relacionar motivo de consulta con diagnósticos previos
    keywords_cardio = {"torácico", "toracico", "corazón", "corazon", "infarto", "arritmia", "pecho"}
    keywords_resp = {"asma", "disnea", "respirar", "oxígeno", "oxigeno", "bronquio"}
    keywords_metabolic = {"diabetes", "glucosa", "hipoglucemia", "hiperglucemia"}

    # Caso: paciente sin póliza en base de datos
    if not poliza:
        return AnalisisIA(
            resumen_ejecutivo=(
                f"Asegurado {ingreso.cedula} sin póliza en base. Triage {ingreso.triage_nivel}. "
                "Atención por cuenta del paciente o validar afiliación IESS."
            ),
            poliza_valida=False,
            estado_poliza=EstadoPoliza.NO_ENCONTRADA,
            riesgo_clinico_financiero=NivelRiesgo.ALTO if ingreso.triage_nivel <= 2 else NivelRiesgo.MEDIO,
            preexistencias_relevantes=[],
            exclusiones_detectadas=["Sin cobertura privada registrada"],
            recomendaciones_admisiones=[
                "Estabilizar paciente según protocolo MSP",
                "Solicitar carnet IESS o comprobante de pago privado",
                "Contactar área de facturación antes de procedimientos de alto costo",
            ],
            recomendaciones_gestor=["Registrar ingreso sin póliza — requiere verificación manual"],
            autorizacion_sugerida="revision_manual",
            confianza=0.72,
            tiempo_analisis_ms=int((time.perf_counter() - inicio) * 1000),
            modelo_ia="motor-local-ec-v1",
        )

    valida = poliza.estado == EstadoPoliza.VIGENTE
    riesgo = NivelRiesgo.BAJO

    if ingreso.triage_nivel <= 2:
        riesgo = NivelRiesgo.CRITICO
    elif poliza.estado != EstadoPoliza.VIGENTE:
        riesgo = NivelRiesgo.ALTO

    # Cruza preexistencias declaradas con el motivo de la consulta actual
    for pre in poliza.preexistencias:
        desc_lower = pre.descripcion.lower()
        relevante = False
        if any(k in motivo for k in keywords_cardio) and any(
            w in desc_lower for w in ("cardio", "hipertens", "isquém", "isquem", "coraz")
        ):
            relevante = True
        if any(k in motivo for k in keywords_resp) and "asma" in desc_lower:
            relevante = True
        if any(k in motivo for k in keywords_metabolic) and "diabetes" in desc_lower:
            relevante = True

        if relevante:
            preexistencias_rel.append(f"{pre.codigo}: {pre.descripcion}")
            if not pre.cubierta:
                exclusiones.append(f"Preexistencia no cubierta: {pre.descripcion}")
                riesgo = NivelRiesgo.ALTO

    if poliza.estado == EstadoPoliza.VENCIDA:
        exclusiones.append("Póliza vencida — sin cobertura vigente")
        rec_adm.append("Informar al paciente/familiar sobre estado de póliza vencida")
        rec_gestor.append("Ofrecer renovación o plan de contingencia")
    elif poliza.estado == EstadoPoliza.SUSPENDIDA:
        exclusiones.append("Póliza suspendida por mora o incumplimiento")
        rec_gestor.append("Verificar motivo de suspensión en sistema core")
    else:
        rec_adm.append(f"Aplicar copago del {poliza.copago_porcentaje}% según plan {poliza.plan}")
        rec_gestor.append(f"Tope anual disponible: USD {poliza.tope_anual_usd:,.0f}")

    if ingreso.triage_nivel <= 2:
        rec_adm.insert(0, "PRIORIDAD: activar protocolo de emergencia — facturación en paralelo")
        rec_gestor.insert(0, "Autorización expresa en < 15 min para casos triage 1-2")

    autorizacion = "aprobar" if valida and not exclusiones else "revision_manual"
    if exclusiones and ingreso.triage_nivel > 2:
        autorizacion = "autorizacion_previa"
    if not valida and ingreso.triage_nivel > 3:
        autorizacion = "negar"

    resumen = (
        f"{'[OK]' if valida else '[X]'} Poliza {poliza.numero} ({poliza.estado.value}). "
        f"{poliza.titular}. {ingreso.motivo_consulta[:80]}. "
        f"Riesgo {riesgo.value}."
    )

    elapsed = int((time.perf_counter() - inicio) * 1000)
    return AnalisisIA(
        resumen_ejecutivo=resumen,
        poliza_valida=valida,
        estado_poliza=poliza.estado,
        riesgo_clinico_financiero=riesgo,
        preexistencias_relevantes=preexistencias_rel,
        exclusiones_detectadas=exclusiones,
        recomendaciones_admisiones=rec_adm or ["Proceder con admisión estándar bajo cobertura vigente"],
        recomendaciones_gestor=rec_gestor or ["Monitorear caso — sin alertas adicionales"],
        autorizacion_sugerida=autorizacion,
        confianza=0.78,
        tiempo_analisis_ms=elapsed,
        modelo_ia="motor-local-ec-v1",
    )
