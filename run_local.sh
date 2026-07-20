#!/usr/bin/env bash
# Run the merged board_api app locally against a Postgres given by DATABASE_URL.
# Usage:
#   DATABASE_URL='postgresql://.../neondb?sslmode=require' ./run_local.sh
# Serves the API on :8000. Point a local Vite dev server (portal :5173)
# at it via its proxy, or curl /api directly.
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL (Neon pooled string, ?sslmode=require only)}"

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$HERE/.venv/bin/activate"

# Local dev secrets (throwaway) + non-secure cookies for http testing.
export SESSION_SECRET="${SESSION_SECRET:-local-dev-session}"
export ADMIN_SESSION_SECRET="${ADMIN_SESSION_SECRET:-local-dev-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-localtest}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
export COOKIE_SECURE=false

cd "$HERE"
exec uvicorn board_api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
