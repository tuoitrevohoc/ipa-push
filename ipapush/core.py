"""Shared business logic used by both the web app and the MCP server."""

import shutil
from pathlib import Path
from urllib.parse import quote

from . import config, ipa as ipa_mod, manifest as manifest_mod, store


def push_ipa_file(src_path: str | Path, display_name: str = "") -> dict:
    """Validate + store an IPA from a local path. Returns metadata + install links."""
    src = Path(src_path).expanduser()
    if not src.is_file():
        raise ipa_mod.IPAError(f"File not found: {src}")
    if src.stat().st_size == 0:
        raise ipa_mod.IPAError(f"File is empty: {src}")
    parsed = ipa_mod.parse_ipa(src)

    ipa_id = store.new_id()
    dest = config.IPAS_DIR / f"{ipa_id}.ipa"
    shutil.copyfile(src, dest)
    if parsed.get("icon_data"):
        (config.IPAS_DIR / f"{ipa_id}.png").write_bytes(parsed["icon_data"])

    meta = store.save({
        "id": ipa_id,
        "display_name": display_name.strip() or parsed["name"],
        "bundle_id": parsed["bundle_id"],
        "version": parsed["version"],
        "build": parsed["build"],
        "size": dest.stat().st_size,
        "source_file": src.name,
        "has_icon": bool(parsed.get("icon_data")),
    })
    return with_links(meta)


def with_links(meta: dict) -> dict:
    """Attach public URLs + itms-services install link to a metadata dict."""
    ipa_id = meta["id"]
    base = config.BASE_URL
    manifest_url = f"{base}/m/{ipa_id}.plist"
    itms_url = "itms-services://?action=download-manifest&url=" + quote(manifest_url, safe="")
    return {
        **meta,
        "ipa_url": f"{base}/f/{ipa_id}.ipa",
        "manifest_url": manifest_url,
        "install_page": f"{base}/i/{ipa_id}",
        "qr_url": f"{base}/qr/{ipa_id}.png",
        "itms_url": itms_url,
    }


def get_ipa(ipa_id: str) -> dict | None:
    meta = store.load(ipa_id)
    return with_links(meta) if meta else None


def list_ipas() -> list[dict]:
    return [with_links(m) for m in store.list_all()]


def delete_ipa(ipa_id: str) -> bool:
    return store.delete(ipa_id)


def manifest_bytes(ipa_id: str) -> bytes | None:
    meta = store.load(ipa_id)
    if not meta:
        return None
    info = with_links(meta)
    return manifest_mod.build_manifest(
        ipa_url=info["ipa_url"],
        bundle_id=meta["bundle_id"],
        version=meta["version"],
        title=meta["display_name"],
    )


def ipa_file_path(ipa_id: str) -> Path | None:
    meta = store.load(ipa_id)
    if not meta:
        return None
    p = config.IPAS_DIR / f"{ipa_id}.ipa"
    return p if p.exists() else None
