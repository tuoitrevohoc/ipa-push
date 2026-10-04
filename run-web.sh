#!/bin/bash
# Chạy web app (+ MCP over HTTP tại /mcp)
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; source .env; set +a; fi
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec $PY -m ipapush.web
