#!/usr/bin/env bash
# Backup horario de vibra.db. Usa el comando .backup de SQLite para un snapshot
# consistente (incluye el WAL). Conserva las últimas 72 copias (~3 días).
set -euo pipefail
cd "$(dirname "$0")/.."

# Carga DB_PATH y BACKUP_DIR del .env si existen.
DB_PATH="vibra.db"
BACKUP_DIR="backups"
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d-%H%M%S)
DEST="$BACKUP_DIR/vibra-$TS.db"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$DEST'"
else
  # Fallback: copia directa (menos ideal con WAL activo, pero funcional).
  cp "$DB_PATH" "$DEST"
fi

# Rotación: conserva las 72 más recientes.
ls -1t "$BACKUP_DIR"/vibra-*.db 2>/dev/null | tail -n +73 | xargs -r rm -f
echo "backup -> $DEST"
