#!/bin/bash
# Chạy MCP server qua stdio (cho Claude Code / Claude Desktop / agent local)
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; source .env; set +a; fi
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec $PY -m ipapush.mcp_server
