#!/usr/bin/env sh
# Local dev server on http://127.0.0.1:8000
set -e
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
exec python -m app.server
