"""
Modelos de datos (Pydantic) para validación de JSON entrante y saliente.

Define la estructura del webhook del hospital, la póliza, el análisis IA
y la alerta completa que se guarda y notifica.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NivelRiesgo(str, Enum):
    """Riesgo clínico-financiero calculado por el agente IA."""

    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"


class EstadoPoliza(str, Enum):
    """Estado de cobertura del asegurado en Ecuador."""

    VIGENTE = "vigente"
    VENCIDA = "vencida"
    SUSPENDIDA = "suspendida"
    NO_ENCONTRADA = "no_encontrada"


class WebhookIngresoEmergencia(BaseModel):
    """
    Payload JSON que envía el HIS del hospital al detectar ingreso a emergencias.
    Este es el cuerpo del POST /api/webhook/ingreso-emergencia
    """

    cedula: str = Field(..., description="Cédula ecuatoriana del paciente", examples=["1712345678"])
    numero_poliza: Optional[str] = Field(None, description="Número de póliza si está disponible")
    hospital_codigo: str = Field(..., description="Código del establecimiento de salud", examples=["HOSP-QUI-001"])
    hospital_nombre: str = Field(..., examples=["Hospital General de Guayaquil"])
    motivo_consulta: str = Field(..., examples=["Dolor torácico agudo"])
    triage_nivel: int = Field(3, ge=1, le=5, description="1=crítico, 5=no urgente")
    timestamp_ingreso: Optional[datetime] = None  # Si no viene, se usa hora actual UTC


class Preexistencia(BaseModel):
    """Condición preexistente declarada en la póliza (código CIE-10)."""

    codigo: str
    descripcion: str
    fecha_diagnostico: str
    cubierta: bool  # Si el plan cubre tratamiento relacionado
    observaciones: Optional[str] = None


class PolizaInfo(BaseModel):
    """Datos completos de la póliza recuperados de la base de datos."""

    numero: str
    aseguradora: str
    estado: EstadoPoliza
    titular: str
    cedula: str
    vigencia_desde: str
    vigencia_hasta: str
    plan: str
    copago_porcentaje: float
    tope_anual_usd: float
    preexistencias: list[Preexistencia] = []


class AnalisisIA(BaseModel):
    """Resultado estructurado del agente de inteligencia artificial."""

    resumen_ejecutivo: str
    poliza_valida: bool
    estado_poliza: EstadoPoliza
    riesgo_clinico_financiero: NivelRiesgo
    preexistencias_relevantes: list[str]
    exclusiones_detectadas: list[str]
    recomendaciones_admisiones: list[str]  # Para el hospital
    recomendaciones_gestor: list[str]  # Para la aseguradora
    autorizacion_sugerida: str  # aprobar | autorizacion_previa | negar | revision_manual
    tiempo_analisis_ms: int
    modelo_ia: str  # Nombre del modelo usado (gpt-4o-mini, motor-local-ec-v1, etc.)
    confianza: float = Field(ge=0, le=1)


class AlertaEmergencia(BaseModel):
    """Respuesta completa del webhook: ingreso + póliza + análisis + estado de notificaciones."""

    id: str
    timestamp: datetime
    paciente_cedula: str
    paciente_nombre: str
    hospital: str
    motivo: str
    triage: int
    poliza: Optional[PolizaInfo]
    analisis: AnalisisIA
    notificaciones_enviadas: dict[str, bool]  # hospital_admisiones, gestor_casos


class NotificacionPayload(BaseModel):
    """Mensaje enviado por webhook o correo a admisiones o gestor de casos."""

    tipo_destino: str
    alerta_id: str
    asunto: str
    cuerpo_html: str
    cuerpo_texto: str
    prioridad: str
