#!/bin/bash
# Launch the Preserve API gateway.
#
# Config via environment (see preserve/api/settings.py). Minimal example:
#   export PRESERVE_UPSTREAM_API_KEY=...        # or DEEPINFRA_API_KEY in .env
#   export PRESERVE_API_KEYS='{"sk-team-alpha":{"name":"alpha","rpm":60,"daily_token_quota":2000000}}'
#   ./scripts/run_api.sh
#
# Dev (no auth — DO NOT use in production):
#   PRESERVE_ALLOW_NO_AUTH=1 ./scripts/run_api.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

HOST="${PRESERVE_API_HOST:-127.0.0.1}"
PORT="${PRESERVE_API_PORT:-8800}"

echo "Preserve API gateway on http://$HOST:$PORT  (docs at /docs)"
exec uvicorn preserve.api.app:app --host "$HOST" --port "$PORT"
