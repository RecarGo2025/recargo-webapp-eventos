#!/usr/bin/env bash
# Compila Tailwind a un CSS estático (app/static/vibra.css). Correr en la máquina
# de desarrollo tras editar plantillas/JS; el resultado se commitea y se despliega.
set -euo pipefail
cd "$(dirname "$0")/.."

BIN="${TAILWIND_BIN:-./bin/tailwindcss}"
if [[ ! -x "$BIN" ]]; then
  echo "No se encontró el binario de Tailwind en $BIN"
  echo "Descárgalo de https://github.com/tailwindlabs/tailwindcss/releases (standalone CLI)"
  exit 1
fi

"$BIN" -c tailwind/tailwind.config.js -i tailwind/input.css -o app/static/vibra.css --minify
echo "OK -> app/static/vibra.css"
