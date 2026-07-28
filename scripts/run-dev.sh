#!/usr/bin/env bash
# Arranque local de desarrollo (con reload). Requiere .env (usa BAJIE_MOCK=1).
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -d .venv ]] || python3 -m venv .venv
./.venv/bin/pip install -q -r requirements.txt
exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8099 --reload
