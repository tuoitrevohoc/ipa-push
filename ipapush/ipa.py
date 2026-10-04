"""Parse IPA files: bundle id, version, display name, icon.

An IPA is a zip containing Payload/<App>.app/Info.plist.
plistlib handles both XML and binary plists.
"""

import plistlib
import zipfile
from pathlib import Path


class IPAError(ValueError):
    pass


def _find_app_info(names: list[str]) -> str:
    """Find Payload/<App>.app/Info.plist for the top-level app bundle."""
    cands = [
        n for n in names
        if n.startswith("Payload/")
        and n.count("/") == 2
        and n.endswith(".app/Info.plist")
    ]
    if not cands:
        raise IPAError("Not a valid IPA: Payload/<App>.app/Info.plist not found")
    # Prefer the shortest path (top-level app, not nested appex)
    return sorted(cands, key=len)[0]


def parse_ipa(path: str | Path) -> dict:
    """Return metadata dict extracted from the IPA."""
    path = Path(path)
    if not zipfile.is_zipfile(path):
        raise IPAError(f"Not a zip/IPA file: {path}")
    with zipfile.ZipFile(path) as z:
        info_name = _find_app_info(z.namelist())
        app_dir = info_name.rsplit("/", 1)[0] + "/"
        try:
            info = plistlib.loads(z.read(info_name))
        except Exception as e:
            raise IPAError(f"Cannot read Info.plist: {e}")
        bundle_id = info.get("CFBundleIdentifier")
        if not bundle_id:
            raise IPAError("Info.plist has no CFBundleIdentifier")
        icon_file = _find_icon(z, app_dir, info)
        icon_data = z.read(app_dir + icon_file) if icon_file else None
    return {
        "bundle_id": bundle_id,
        "version": info.get("CFBundleShortVersionString") or info.get("CFBundleVersion") or "?",
        "build": info.get("CFBundleVersion") or "?",
        "name": info.get("CFBundleDisplayName") or info.get("CFBundleName") or bundle_id,
        "icon_data": icon_data,
    }


def _find_icon(z: zipfile.ZipFile, app_dir: str, info: dict) -> str | None:
    """Best-effort: locate the largest app icon PNG inside the .app dir."""
    names = [n for n in z.namelist() if n.startswith(app_dir) and n.lower().endswith(".png")]
    if not names:
        return None
    # Prefer files declared in CFBundleIcons, then AppIcon*, then largest file.
    declared: list[str] = []
    try:
        icons = info.get("CFBundleIcons", {}).get("CFBundlePrimaryIcon", {}).get("CFBundleIconFiles", [])
        declared = [f"{app_dir}{b}.png" for b in icons] + [f"{app_dir}{b}@2x.png" for b in icons] + [f"{app_dir}{b}@3x.png" for b in icons]
    except Exception:
        pass
    for d in declared:
        if d in names:
            return d.rsplit("/", 1)[-1]
    appicon = [n for n in names if "appicon" in n.lower()]
    pool = appicon or names
    # Largest by compressed size as a proxy for resolution.
    best = max(pool, key=lambda n: z.getinfo(n).file_size)
    return best.rsplit("/", 1)[-1]
