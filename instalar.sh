#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo " Alerta Temprana Emergencias - Instalación"
echo "============================================"

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 no encontrado. Instale Python 3.10+"
  exit 1
fi

python3 --version

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

[ -f .env ] || cp .env.example .env

echo ""
echo "Listo. Ejecute: ./iniciar.sh"
