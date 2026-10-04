"""Configuration from environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("IPA_PUSH_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
IPAS_DIR = DATA_DIR / "ipas"
IPAS_DIR.mkdir(parents=True, exist_ok=True)
META_DIR = DATA_DIR / "meta"
META_DIR.mkdir(parents=True, exist_ok=True)

# Public base URL of the web app, e.g. https://ipa-push.example.com
# The iPhone must be able to reach this over HTTPS for OTA install.
BASE_URL = os.environ.get("IPA_PUSH_BASE_URL", "http://localhost:8765").rstrip("/")

# Token protecting upload/delete APIs and the MCP-over-HTTP endpoint.
# Leave empty to disable auth (not recommended when exposed publicly).
TOKEN = os.environ.get("IPA_PUSH_TOKEN", "")

PORT = int(os.environ.get("IPA_PUSH_PORT", "8765"))
