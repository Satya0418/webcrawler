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

echo "=========================================================="
echo " Starting Intelligent PDF Section Extraction System"
echo " Dashboard UI: http://127.0.0.1:8000"
echo " Interactive API Docs: http://127.0.0.1:8000/docs"
echo "=========================================================="

exec .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
