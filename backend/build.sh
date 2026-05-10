#!/usr/bin/env bash
# Copy the pre-built frontend dist into backend/static so FastAPI can serve it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIST="$SCRIPT_DIR/../frontend/dist"
STATIC_DIR="$SCRIPT_DIR/static"

if [ -d "$FRONTEND_DIST" ]; then
    echo "==> Copying pre-built frontend dist → backend/static"
    rm -rf "$STATIC_DIR"
    cp -r "$FRONTEND_DIST" "$STATIC_DIR"
    echo "==> Done"
else
    echo "==> No frontend/dist found, skipping static copy"
fi
