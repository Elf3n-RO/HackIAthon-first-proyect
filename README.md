# Sistema de Alerta Temprana de Ingresos a Emergencias

Sistema para **Ecuador** que recibe un webhook cuando un asegurado ingresa a emergencias, un **agente de IA** valida la póliza y preexistencias, y envía **notificaciones simultáneas** al departamento de admisiones del hospital y al gestor de casos de la aseguradora.

## Características

- **Webhook** `POST /api/webhook/ingreso-emergencia` integrado con HIS hospitalario
- **Agente IA** (OpenAI, Ollama local, o motor inteligente local sin API)
- Validación de vigencia de póliza, copagos, topes y preexistencias (CIE-10)
- **Notificaciones en paralelo** a hospital y aseguradora (webhook, email SMTP, consola)
- Panel web en español con simulador de ingresos
- Datos demo de aseguradoras ecuatorianas

## Requisitos

- Python 3.10 o superior
- Windows, macOS o Linux

## Instalación rápida (Windows)

1. Doble clic en **`instalar.bat`**
2. Doble clic en **`iniciar.bat`**
3. Abra **http://localhost:8000**

## Instalación (Linux / macOS)

```bash
chmod +x instalar.sh iniciar.sh
./instalar.sh
./iniciar.sh
```

## Configurar IA

Copie `.env.example` a `.env`:

| Modo | Configuración |
|------|----------------|
| **OpenAI** | `OPENAI_API_KEY=sk-...` |
| **Ollama local** | `OPENAI_BASE_URL=http://localhost:11434/v1` y `OPENAI_MODEL=llama3.2` |
| **Sin API** | Deje vacío — usa motor local con reglas clínicas en español |

## Webhook (hospital)

```http
POST http://localhost:8000/api/webhook/ingreso-emergencia
Content-Type: application/json

{
  "cedula": "1712345678",
  "numero_poliza": "POL-EC-2024-001234",
  "hospital_codigo": "HOSP-QUI-001",
  "hospital_nombre": "Hospital General de Guayaquil",
  "motivo_consulta": "Dolor torácico agudo",
  "triage_nivel": 2
}
```

## Pacientes de prueba

| Cédula | Estado póliza |
|--------|----------------|
| 1712345678 | Vigente (diabetes, HTA) |
| 1723456789 | Vigente (asma) |
| 1709876543 | Vencida |
| 1756789012 | Suspendida |
| 9999999999 | Sin registro |

## Notificaciones externas

En `.env` configure:

- `WEBHOOK_HOSPITAL_ADMISIONES` — URL que recibe alertas de admisiones
- `WEBHOOK_GESTOR_CASOS` — URL del CRM de la aseguradora
- `EMAIL_SMTP_*` — para correo real (opcional)

Sin configuración, las alertas se muestran en consola y en el panel web.

## API

- Documentación interactiva: **http://localhost:8000/docs**
- Salud: `GET /api/health`
- Listar alertas: `GET /api/alertas`

## Arquitectura

```
Hospital HIS → Webhook → Agente IA → Notificaciones paralelas
                              ↓              ├── Admisiones
                         SQLite (alertas)   └── Gestor casos
```

## Equipo / Hackathon

Proyecto educativo — integrar con sistemas reales requiere acuerdos con aseguradoras y hospitales bajo normativa SCVS Ecuador.
