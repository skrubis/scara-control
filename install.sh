#!/usr/bin/env bash
set -euo pipefail

# Portable installer for this project
# - Creates a local virtual environment in .venv
# - Installs Python dependencies from requirements.txt
# - Verifies tkinter availability and prints guidance if missing

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
REQ_FILE="${REQ_FILE:-requirements.txt}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: python3 not found. Please install Python 3." >&2
  exit 1
fi

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Activate venv (works in bash/zsh/sh)
# shellcheck source=/dev/null
. "$VENV_DIR/bin/activate"

# Upgrade pip and install requirements
python -m pip install --upgrade pip wheel
if [ -f "$REQ_FILE" ]; then
  python -m pip install -r "$REQ_FILE"
else
  echo "Warning: $REQ_FILE not found, nothing to install."
fi

# Sanity check for tkinter (used by the GUI). It's part of stdlib but may need system tk packages.
python - <<'PY'
try:
    import tkinter  # noqa: F401
    print("tkinter: OK")
except Exception as e:
    print("tkinter: NOT AVAILABLE -> On Debian/Ubuntu: sudo apt-get install python3-tk; Fedora: sudo dnf install python3-tkinter; Arch: sudo pacman -S tk")
    print(f"Detail: {e}")
PY

# Sanity check for serial and pygame
python - <<'PY'
missing = []
for mod in ("serial", "pygame"):
    try:
        __import__(mod)
    except Exception as e:
        missing.append((mod, str(e)))
if missing:
    print("Some Python modules are missing even after installation:")
    for mod, err in missing:
        print(f" - {mod}: {err}")
    print("Try re-running: python -m pip install -r requirements.txt")
else:
    print("All required Python modules imported successfully.")
PY

echo "\nDone. Activate the environment with:"
echo "  source $VENV_DIR/bin/activate"
