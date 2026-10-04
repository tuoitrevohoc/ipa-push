"""MCP server for ipa-push.

Two ways to run:
  1. stdio (local agent, e.g. Claude Code on the Mac):
       python -m ipapush.mcp_server
  2. streamable HTTP (remote agent) — mounted by the web app at /mcp.
"""

import json
import re
import shutil
import subprocess

from mcp.server.mcpserver import MCPServer

from . import config, core, ipa as ipa_mod

mcp = MCPServer("ipa-push")


def _ok(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool(description="Đẩy 1 file .ipa (đường dẫn local trên máy chạy server) lên web app, trả về link cài đặt OTA (itms-services), trang cài đặt, QR. IPA phải ký Ad Hoc/Enterprise thì iPhone mới cài được qua web.")
def push_ipa(path: str, display_name: str = "") -> str:
    try:
        info = core.push_ipa_file(path, display_name=display_name)
        return _ok({"ok": True, **info})
    except ipa_mod.IPAError as e:
        return _ok({"ok": False, "error": str(e)})


@mcp.tool(description="Liệt kê tất cả IPA đã upload kèm link cài đặt.")
def list_ipas() -> str:
    return _ok(core.list_ipas())


@mcp.tool(description="Lấy thông tin + link cài đặt (itms-services, trang cài đặt, QR) của 1 IPA theo id.")
def get_install_info(ipa_id: str) -> str:
    info = core.get_ipa(ipa_id)
    return _ok(info or {"ok": False, "error": f"IPA not found: {ipa_id}"})


@mcp.tool(description="Xóa 1 IPA đã upload theo id.")
def delete_ipa(ipa_id: str) -> str:
    return _ok({"ok": core.delete_ipa(ipa_id)})


def _devicectl(args: list[str]) -> subprocess.CompletedProcess:
    xcrun = shutil.which("xcrun")
    if not xcrun:
        raise RuntimeError("xcrun not found — tool này chỉ chạy trên máy Mac có Xcode.")
    return subprocess.run(
        [xcrun, "devicectl", *args],
        capture_output=True, text=True, timeout=120,
    )


@mcp.tool(description="Liệt kê iPhone/iPad đang kết nối với máy Mac (USB hoặc WiFi). Chỉ chạy trên Mac có Xcode.")
def list_devices() -> str:
    try:
        p = _devicectl(["list", "devices"])
    except RuntimeError as e:
        return _ok({"ok": False, "error": str(e)})
    out = (p.stdout or "") + (p.stderr or "")
    devices = []
    for line in out.splitlines():
        m = re.search(r"(.+?)\s+\(([0-9A-Fa-f-]{8,})\)", line)
        if m and "simulator" not in line.lower():
            devices.append({"name": m.group(1).strip("- ").strip(), "udid": m.group(2)})
    return _ok({"ok": p.returncode == 0, "devices": devices, "raw": out.strip()[:2000]})


@mcp.tool(description="Cài IPA TRỰC TIẾP lên iPhone qua USB/WiFi (không cần mở web, không cần ký Ad Hoc — bản Development cũng được). udid: lấy từ list_devices; bỏ trống nếu chỉ có 1 máy. Chỉ chạy trên Mac có Xcode, iPhone đã pair + bật WiFi sync.")
def install_to_device(ipa_id: str, udid: str = "") -> str:
    ipa_path = core.ipa_file_path(ipa_id)
    if not ipa_path:
        return _ok({"ok": False, "error": f"IPA not found: {ipa_id}"})
    args = ["device", "install", "app", "--device", udid, str(ipa_path)] if udid \
        else ["device", "install", "app", str(ipa_path)]
    try:
        p = _devicectl(args)
    except RuntimeError as e:
        return _ok({"ok": False, "error": str(e)})
    out = (p.stdout or "") + (p.stderr or "")
    return _ok({"ok": p.returncode == 0, "output": out.strip()[:2000]})


@mcp.tool(description="Trả về cấu hình hiện tại: BASE_URL public, thư mục data, token có bật không.")
def server_info() -> str:
    return _ok({
        "base_url": config.BASE_URL,
        "data_dir": str(config.DATA_DIR),
        "auth_enabled": bool(config.TOKEN),
        "port": config.PORT,
    })


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
