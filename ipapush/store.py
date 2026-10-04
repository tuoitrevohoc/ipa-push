"""JSON metadata store for uploaded IPAs."""

import json
import time
import uuid
from pathlib import Path

from . import config


def _meta_path(ipa_id: str) -> Path:
    return config.META_DIR / f"{ipa_id}.json"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def save(meta: dict) -> dict:
    meta = dict(meta)
    meta.setdefault("id", new_id())
    meta.setdefault("uploaded_at", int(time.time()))
    _meta_path(meta["id"]).write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def load(ipa_id: str) -> dict | None:
    p = _meta_path(ipa_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def list_all() -> list[dict]:
    metas = []
    for p in config.META_DIR.glob("*.json"):
        try:
            metas.append(json.loads(p.read_text()))
        except Exception:
            continue
    metas.sort(key=lambda m: m.get("uploaded_at", 0), reverse=True)
    return metas


def delete(ipa_id: str) -> bool:
    p = _meta_path(ipa_id)
    if not p.exists():
        return False
    p.unlink()
    ipa_file = config.IPAS_DIR / f"{ipa_id}.ipa"
    if ipa_file.exists():
        ipa_file.unlink()
    icon_file = config.IPAS_DIR / f"{ipa_id}.png"
    if icon_file.exists():
        icon_file.unlink()
    return True
