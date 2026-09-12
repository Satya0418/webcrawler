#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"

echo "=========================================================="
echo " Starting Intelligent PDF Section Extraction System"
echo " Host: ${HOST} | Port: ${PORT} | Workers: ${WORKERS}"
echo " Dashboard UI: http://${HOST}:${PORT}"
echo " Interactive API Docs: http://${HOST}:${PORT}/docs"
echo "=========================================================="

if [ "$WORKERS" -gt 1 ] || [ "${ENV}" = "production" ]; then
    exec .venv/bin/uvicorn backend.main:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
else
    exec .venv/bin/uvicorn backend.main:app --host "$HOST" --port "$PORT" --reload
fi
