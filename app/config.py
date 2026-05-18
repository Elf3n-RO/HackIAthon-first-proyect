"""
Configuración central del sistema (variables de entorno).

Todas las opciones se leen del archivo .env en la raíz del proyecto.
Copie .env.example a .env y configure OPENAI_API_KEY para usar IA en la nube.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parámetros del servidor, IA y notificaciones."""

    # Lee .env automáticamente; ignora variables extra no definidas aquí
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Servidor web ---
    host: str = "0.0.0.0"  # 0.0.0.0 = accesible desde otras máquinas en la red local
    port: int = 8000

    # --- Inteligencia artificial (API compatible con OpenAI) ---
    openai_api_key: str = ""  # Clave sk-... de OpenAI, Groq, etc. Para Ollama use "ollama"
    openai_base_url: str = "https://api.openai.com/v1"  # Ollama: http://localhost:11434/v1
    openai_model: str = "gpt-4o-mini"  # Modelo a invocar (gpt-4o-mini, llama3.2, etc.)

    # --- Webhooks externos (opcional) para notificaciones reales ---
    webhook_hospital_admisiones: str = ""
    webhook_gestor_casos: str = ""

    # --- Correo SMTP (opcional) ---
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_user: str = ""
    email_smtp_password: str = ""
    email_hospital: str = "admisiones@hospital.demo.ec"
    email_gestor: str = "gestor@aseguradora.demo.ec"

    @property
    def ia_configurada(self) -> bool:
        """
        True si hay API key O si la URL apunta a Ollama (puerto 11434).
        Cuando es False, el agente usa el motor local de reglas (demo sin internet).
        """
        return bool(self.openai_api_key.strip()) or "11434" in self.openai_base_url


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuración (se cachea para no releer .env en cada petición)."""
    return Settings()
