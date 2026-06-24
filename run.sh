#!/usr/bin/env bash
# Launch the MRA Mapmaker. Prefers a Python that already has pygame; else installs it.
cd "$(dirname "$0")" || exit 1
PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import pygame" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "Python 3 not found. Install it from https://www.python.org/downloads/ and re-run."
  read -r -p "Press Enter to close..."
  exit 1
fi
"$PY" -c "import pygame" >/dev/null 2>&1 || "$PY" -m pip install pygame
exec "$PY" editor.py
