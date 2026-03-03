#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -d venv ]]; then
  echo "Missing venv. Create it first: python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

. venv/bin/activate
python3 headless_runtime.py "$@"
