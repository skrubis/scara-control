#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [ ! -f ".venv/bin/activate" ]; then
  echo ".venv not found. Run ./install.sh first."
  exit 1
fi
source ".venv/bin/activate"
exec python scara_control.py
