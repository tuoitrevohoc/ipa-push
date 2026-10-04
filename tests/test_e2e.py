"""End-to-end test for ipa-push. Run:  python tests/test_e2e.py

Builds a fake IPA, then exercises: parsing, core push/manifest,
all web routes, MCP tools (direct + stdio + HTTP).
"""

import json
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Isolated env BEFORE importing ipapush (config reads env at import).
TMP = Path(tempfile.mkdtemp(prefix="ipa-push-test-"))
os.environ["IPA_PUSH_DIR"] = str(TMP / "data")
os.environ["IPA_PUSH_BASE_URL"] = "https://ipa.example.com"
os.environ["IPA_PUSH_TOKEN"] = "secret123"
os.environ["IPA_PUSH_ALLOWED_HOSTS"] = "testserver"


def make_fake_ipa(path: Path):
    def png(w, h, rgb):
        def chunk(t, d):
            c = t + d
            return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c))
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")

    appdir = TMP / "Payload" / "FakeApp.app"
    appdir.mkdir(parents=True)
    info = {
        "CFBundleIdentifier": "com.example.fakeapp",
        "CFBundleShortVersionString": "2.1.0",
        "CFBundleVersion": "42",
        "CFBundleDisplayName": "Fake App",
        "CFBundleName": "FakeApp",
    }
    (appdir / "Info.plist").write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
    (appdir / "AppIcon60x60@3x.png").write_bytes(png(180, 180, (255, 0, 0)))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (TMP / "Payload").rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(TMP))


def check(name, cond, extra=""):
    assert cond, f"FAILED: {name} {extra}"
    print(f"  ✓ {name}")


def main():
    from ipapush import core, ipa as ipa_mod
    from ipapush import mcp_server

    fake = TMP / "FakeApp.ipa"
    make_fake_ipa(fake)

    print("== IPA parsing ==")
    parsed = ipa_mod.parse_ipa(fake)
    check("bundle id", parsed["bundle_id"] == "com.example.fakeapp")
    check("version", parsed["version"] == "2.1.0")
    check("name", parsed["name"] == "Fake App")
    check("icon extracted", bool(parsed["icon_data"]))
    try:
        ipa_mod.parse_ipa(TMP / "nope.ipa")
        check("missing file raises", False)
    except Exception:
        check("missing file raises", True)

    print("== core ==")
    info = core.push_ipa_file(fake, display_name="App Test")
    ipa_id = info["id"]
    check("itms url", info["itms_url"].startswith(
        "itms-services://?action=download-manifest&url=https%3A%2F%2Fipa.example.com%2Fm%2F"))
    mb = core.manifest_bytes(ipa_id)
    check("manifest content",
          b"com.example.fakeapp" in mb and b"https://ipa.example.com/f/" in mb
          and b"2.1.0" in mb and b"App Test" in mb)

    print("== web routes ==")
    from fastapi.testclient import TestClient
    from ipapush.web import create_app
    client = TestClient(create_app())
    check("GET /", client.get("/").status_code == 200)
    check("auth 401", client.get("/api/ipas").status_code == 401)
    check("auth 200", client.get("/api/ipas", params={"token": "secret123"}).status_code == 200)
    r = client.get(f"/m/{ipa_id}.plist")
    check("manifest route", r.status_code == 200 and "software-package" in r.text
          and "xml" in r.headers["content-type"])
    r = client.get(f"/f/{ipa_id}.ipa")
    check("ipa route", r.status_code == 200 and r.headers["content-type"] == "application/octet-stream")
    r = client.get(f"/i/{ipa_id}")
    check("install page", r.status_code == 200 and "itms-services://" in r.text)
    r = client.get(f"/qr/{ipa_id}.png")
    check("qr route", r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n")
    check("icon route", client.get(f"/icon/{ipa_id}.png").status_code == 200)
    with open(fake, "rb") as f:
        r = client.post("/api/upload", files={"file": ("x.ipa", f)},
                        data={"name": "Up Test", "token": "secret123"})
    check("upload", r.status_code == 200 and r.json()["display_name"] == "Up Test")
    up_id = r.json()["id"]
    r = client.post("/api/upload", files={"file": ("x.txt", b"hi")}, data={"token": "secret123"})
    check("non-ipa rejected", r.status_code == 400)
    check("delete", client.delete(f"/api/ipas/{up_id}", params={"token": "secret123"}).json() == {"ok": True})
    check("gone after delete", client.get(f"/m/{up_id}.plist").status_code == 404)

    print("== MCP tools (direct) ==")
    res = json.loads(mcp_server.push_ipa(str(fake), "MCP Test"))
    check("push_ipa", res["ok"] and res["bundle_id"] == "com.example.fakeapp")
    mid = res["id"]
    check("list_ipas", any(i["id"] == mid for i in json.loads(mcp_server.list_ipas())))
    check("get_install_info", json.loads(mcp_server.get_install_info(mid))["itms_url"].startswith("itms-services://"))
    check("delete_ipa", json.loads(mcp_server.delete_ipa(mid))["ok"] is True)

    print("== MCP stdio ==")
    p = subprocess.run(
        [sys.executable, "-m", "ipapush.mcp_server"],
        input=b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}\n',
        capture_output=True, timeout=30, cwd=ROOT,
        env={**os.environ},
    )
    check("stdio handshake", b'"result"' in p.stdout and b"ipa-push" in p.stdout)

    print("== MCP over HTTP ==")
    app2 = create_app(mcp_server.mcp)
    with TestClient(app2) as c2:
        r = c2.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        check("/mcp 401 without token", r.status_code == 401)
        h = {"Authorization": "Bearer secret123", "Accept": "application/json, text/event-stream"}
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "t", "version": "1"}}}
        r = c2.post("/mcp/", json=init, headers=h)
        check("initialize", r.status_code == 200 and r.headers.get("mcp-session-id"))
        h2 = dict(h, **{"mcp-session-id": r.headers["mcp-session-id"]})
        c2.post("/mcp/", json={"jsonrpc": "2.0", "id": 2, "method": "notifications/initialized"}, headers=h2)
        r = c2.post("/mcp/", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}, headers=h2)
        check("tools/list", r.status_code == 200 and all(
            t in r.text for t in ["push_ipa", "list_ipas", "get_install_info",
                                  "delete_ipa", "list_devices", "install_to_device", "server_info"]))
        call = {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "server_info", "arguments": {}}}
        r = c2.post("/mcp/", json=call, headers=h2)
        check("tools/call", r.status_code == 200 and "ipa.example.com" in r.text)

    print("\nALL TESTS PASSED ✅")
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
