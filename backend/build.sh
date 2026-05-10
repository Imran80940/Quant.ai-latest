#!/usr/bin/env bash
# Railway build script — runs in the backend service root.
# Builds the React frontend and copies dist/ into backend/static/
# so FastAPI can serve it when SERVE_FRONTEND=true.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"
STATIC_DIR="$SCRIPT_DIR/static"

echo "==> Installing Python dependencies"
pip install -r "$SCRIPT_DIR/requirements.txt"

echo "==> Installing frontend dependencies"
npm --prefix "$FRONTEND_DIR" ci

echo "==> Building frontend"
npm --prefix "$FRONTEND_DIR" run build

echo "==> Copying dist → backend/static"
rm -rf "$STATIC_DIR"
cp -r "$FRONTEND_DIR/dist" "$STATIC_DIR"

echo "==> Build complete"
