"""Workspace extension for the existing Price Signal FastAPI dashboard.

Start from backend/: python -m price_engine.workspace --db demo_fresh.sqlite3
Existing price-history and catalog routes are preserved unchanged.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from dotenv import load_dotenv

from .verified.configuration import ROOT as REPO_ROOT
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from .product_lookup import lookup_product
from .workspace_data import MAX_UPLOAD_BYTES, WorkspaceStore, parse_upload
from .verified.api import register_verified_routes

_PACKAGE = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PACKAGE / "templates"))


class LookupRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)


def register_workspace_routes(app: FastAPI, workspace_db: str | Path) -> None:
    store = WorkspaceStore(workspace_db)
    # The workspace accepts local writes, so reject DNS-rebinding Host headers.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_write_origin(request: Request, call_next):
        # Local, unauthenticated development server: block cross-site browser writes.
        is_workspace = request.url.path.startswith("/api/workspace/")
        is_verified = request.url.path.startswith("/api/verified/")
        if request.method == "POST" and (is_workspace or is_verified):
            origin = request.headers.get("origin")
            if is_verified and not origin:
                return JSONResponse({"detail": "Origin header required for local write"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site writes are disabled"}, status_code=403)
            if origin:
                parsed = urlsplit(origin)
                if (parsed.scheme not in {"http", "https"}
                        or parsed.netloc != request.headers.get("host")
                        or parsed.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}):
                    return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
        response = await call_next(request)
        if request.url.path == "/verified" or request.url.path.startswith("/api/verified/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            if request.url.path == "/verified":
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'")
        return response

    @app.get("/workspace", response_class=HTMLResponse)
    def workspace_page(request: Request):
        return _TEMPLATES.TemplateResponse(request, "workspace.html", {})

    @app.get("/intelligence", response_class=HTMLResponse)
    def intelligence_page(request: Request):
        """Preserve the explicitly labeled legacy simulator for existing users."""
        return _TEMPLATES.TemplateResponse(request, "intelligence.html", {})

    @app.get("/simulation")
    def simulation_alias():
        """Optional explicit route for the fictional Intelligence Studio."""
        return RedirectResponse(url="/intelligence", status_code=307)

    @app.get("/api/workspace/status")
    def status():
        return store.stats()

    @app.get("/api/workspace/products")
    def products(q: str = Query("", max_length=120),
                 limit: int = Query(100, ge=1, le=100),
                 offset: int = Query(0, ge=0, le=1000)):
        return store.products(query=q, limit=limit, offset=offset)

    @app.post("/api/workspace/demo")
    def load_demo():
        return store.load_demo()

    @app.post("/api/workspace/activate/{source}")
    def activate(source: Literal["demo", "upload"]):
        try:
            return store.activate(source)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/workspace/upload")
    async def upload(file: UploadFile = File(...)):
        try:
            data = await file.read(MAX_UPLOAD_BYTES + 1)
            rows = parse_upload(file.filename or "", data)
            return store.save_upload(rows)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            await file.close()

    @app.post("/api/workspace/agent/lookup")
    def agent_lookup(body: LookupRequest):
        try:
            result = lookup_product(body.query)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result["active_dataset"] = store.stats()["active"]
        result["dataset_matches"] = store.products(query=body.query, limit=5)["items"]
        result["deal_verified"] = False
        return result


def create_app(history_db: str | Path, workspace_db: str | Path = "workspace.sqlite3") -> FastAPI:
    from .dashboard import create_app as existing_dashboard
    if Path(history_db).resolve() == Path(workspace_db).resolve():
        raise ValueError("Workspace database must differ from the history database")
    load_dotenv(REPO_ROOT / ".env", override=False)
    app = existing_dashboard(history_db)
    register_workspace_routes(app, workspace_db)
    register_verified_routes(app, history_db)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Price Signal with datasets and product lookup")
    parser.add_argument("--db", default="demo_fresh.sqlite3", help="Existing read-only history database")
    parser.add_argument("--workspace-db", default="workspace.sqlite3", help="Isolated writable workspace database")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Unauthenticated workspace is restricted to loopback hosts")
    import uvicorn
    uvicorn.run(create_app(args.db, args.workspace_db), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
