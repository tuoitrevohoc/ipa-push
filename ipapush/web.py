"""FastAPI web app: upload IPAs, serve OTA manifest + install pages."""

import io
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import qrcode
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
)

from . import config, core, ipa as ipa_mod

TEMPLATES = Path(__file__).parent / "templates"


def _token_ok(request: Request, token: str = "") -> bool:
    """Accept token via ?token=, X-Token header, or Authorization: Bearer."""
    if not config.TOKEN:
        return True
    candidates = [token]
    candidates.append(request.headers.get("x-token", ""))
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        candidates.append(auth[7:].strip())
    qs = parse_qsl(request.url.query)
    candidates.extend(v for k, v in qs if k == "token")
    return any(c and c == config.TOKEN for c in candidates)


def _require_token(request: Request, token: str = ""):
    if not _token_ok(request, token):
        raise HTTPException(status_code=401, detail="Invalid or missing token")


def _qr_png(data: str) -> bytes:
    img = qrcode.make(data, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _is_iphone(request: Request) -> bool:
    ua = request.headers.get("user-agent", "").lower()
    return "iphone" in ua or "ipad" in ua or "ipod" in ua


def _transport_security():
    """MCP DNS-rebinding protection: allow the public host + localhost."""
    import os
    from mcp.server.transport_security import TransportSecuritySettings

    allowed = {"localhost", "127.0.0.1", "[::1]"}
    host = urlparse(config.BASE_URL).hostname
    if host:
        allowed.add(host)
    extra = os.environ.get("IPA_PUSH_ALLOWED_HOSTS", "")
    allowed.update(h.strip() for h in extra.split(",") if h.strip())
    return TransportSecuritySettings(allowed_hosts=sorted(allowed))


def create_app(mcp_server=None) -> FastAPI:
    mcp_app = (
        mcp_server.streamable_http_app(
            streamable_http_path="/", transport_security=_transport_security()
        )
        if mcp_server
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # The MCP streamable-HTTP app needs its own lifespan (task group).
        if mcp_app is not None:
            async with mcp_app.router.lifespan_context(mcp_app):
                yield
        else:
            yield

    app = FastAPI(title="ipa-push", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (TEMPLATES / "index.html").read_text()

    @app.get("/api/ipas")
    def api_list(request: Request, token: str = Query(default="")):
        _require_token(request, token)
        return core.list_ipas()

    @app.post("/api/upload")
    async def api_upload(
        request: Request,
        file: UploadFile = File(...),
        name: str = Form(default=""),
        token: str = Form(default=""),
    ):
        _require_token(request, token)
        if not file.filename or not file.filename.lower().endswith(".ipa"):
            raise HTTPException(status_code=400, detail="Only .ipa files are accepted")
        import uuid
        tmp = config.IPAS_DIR / f"upload-{uuid.uuid4().hex}.tmp"
        try:
            with tmp.open("wb") as f:
                while chunk := await file.read(1024 * 1024):
                    f.write(chunk)
            info = core.push_ipa_file(tmp, display_name=name)
        except ipa_mod.IPAError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            tmp.unlink(missing_ok=True)
        return JSONResponse(info)

    @app.delete("/api/ipas/{ipa_id}")
    def api_delete(request: Request, ipa_id: str, token: str = Query(default="")):
        _require_token(request, token)
        if not core.delete_ipa(ipa_id):
            raise HTTPException(status_code=404, detail="IPA not found")
        return {"ok": True}

    @app.get("/f/{ipa_id}.ipa")
    def serve_ipa(ipa_id: str):
        p = core.ipa_file_path(ipa_id)
        if not p:
            raise HTTPException(status_code=404, detail="IPA not found")
        return FileResponse(p, media_type="application/octet-stream", filename=f"{ipa_id}.ipa")

    @app.get("/m/{ipa_id}.plist")
    def serve_manifest(ipa_id: str):
        data = core.manifest_bytes(ipa_id)
        if not data:
            raise HTTPException(status_code=404, detail="IPA not found")
        return Response(content=data, media_type="application/xml")

    @app.get("/icon/{ipa_id}.png")
    def serve_icon(ipa_id: str):
        p = config.IPAS_DIR / f"{ipa_id}.png"
        if not p.exists():
            raise HTTPException(status_code=404, detail="No icon")
        return FileResponse(p, media_type="image/png")

    @app.get("/qr/{ipa_id}.png")
    def serve_qr(ipa_id: str):
        info = core.get_ipa(ipa_id)
        if not info:
            raise HTTPException(status_code=404, detail="IPA not found")
        return Response(content=_qr_png(info["itms_url"]), media_type="image/png")

    @app.get("/i/{ipa_id}", response_class=HTMLResponse)
    def install_page(request: Request, ipa_id: str):
        info = core.get_ipa(ipa_id)
        if not info:
            raise HTTPException(status_code=404, detail="IPA not found")
        tpl = (TEMPLATES / "install.html").read_text()
        size_mb = f"{info['size'] / 1024 / 1024:.1f} MB"
        icon_block = f'<img class="icon" src="/icon/{ipa_id}.png">' if info.get("has_icon") else ""
        return HTMLResponse(tpl.format(
            name=info["display_name"],
            version=info["version"],
            build=info["build"],
            bundle=info["bundle_id"],
            size=size_mb,
            itms=info["itms_url"],
            qr=info["qr_url"],
            icon_block=icon_block,
            hint="" if _is_iphone(request) else
                '<p class="warn">⚠️ Mở trang này bằng <b>Safari trên iPhone</b> rồi bấm Cài đặt.</p>',
        ))

    if mcp_app is not None:
        app.mount("/mcp", _TokenAuthMiddleware(mcp_app))

    return app


class _TokenAuthMiddleware:
    """401 unless a valid token is supplied (Bearer header or ?token=)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and config.TOKEN:
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            qs = dict(parse_qsl(scope.get("query_string", b"").decode()))
            bearer = headers.get("authorization", "")
            ok = (
                qs.get("token") == config.TOKEN
                or headers.get("x-token") == config.TOKEN
                or (bearer.lower().startswith("bearer ") and bearer[7:].strip() == config.TOKEN)
            )
            if not ok:
                resp = JSONResponse({"detail": "Invalid or missing token"}, status_code=401)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


def main():
    import uvicorn

    mcp_server = None
    try:
        from .mcp_server import mcp as mcp_server
    except Exception:
        pass
    uvicorn.run(create_app(mcp_server), host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
