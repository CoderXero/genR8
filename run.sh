#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

if [ ! -f .env ]; then
  cp .env.example .env
fi

set -a
source .env
set +a

if [ -z "${XAI_API_KEY:-}" ]; then
  echo "Set XAI_API_KEY in .env before running the web UI." >&2
  exit 1
fi

genr8-web
