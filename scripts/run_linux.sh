#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -x ".venv/bin/python" ]]; then
  echo "Project environment missing. Run: python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.lock" >&2
  exit 1
fi
exec .venv/bin/python -m filememory.web
