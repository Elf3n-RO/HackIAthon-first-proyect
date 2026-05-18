#!/usr/bin/env bash
cd "$(dirname "$0")"
source venv/bin/activate
echo "Servidor: http://localhost:8000"
python run.py
