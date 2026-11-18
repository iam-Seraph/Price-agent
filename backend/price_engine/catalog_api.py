"""Read-only, server-side FTS5 catalog search, separate from retailer price history."""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_PACKAGE = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PACKAGE / "templates"))
_WORDS = re.compile(r"\w+", re.UNICODE)


class CatalogReader:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError("Database not found")
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=3.0)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA busy_timeout=2000")
            return db
        except Exception:
            db.close()
            raise

    @staticmethod
    def ready(db: sqlite3.Connection) -> bool:
        return db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='product_catalog'"
        ).fetchone() is not None

    def stats(self) -> dict[str, object]:
        with closing(self.connect()) as db:
            if not self.ready(db):
                return {"ready": False, "products": 0, "source": "open_food_facts",
                        "last_import_utc": None, "prices_available": False}
            products = int(db.execute("SELECT COUNT(*) FROM product_catalog").fetchone()[0])
            recent = db.execute(
                "SELECT completed_at FROM catalog_import_runs ORDER BY completed_at DESC LIMIT 1"
            ).fetchone()
            return {"ready": True, "products": products, "source": "open_food_facts",
                    "last_import_utc": recent[0] if recent else None,
                    "prices_available": False}

    def search(self, query: str = "", limit: int = 25, offset: int = 0) -> dict[str, object]:
        with closing(self.connect()) as db:
            if not self.ready(db):
                return {"ready": False, "items": [], "limit": limit,
                        "offset": offset, "has_more": False}
            columns = ("p.source_product_id,p.name,p.brand,p.category,p.quantity,"
                       "p.countries,p.source_url,p.source")
            if query.strip():
                # Quote every unicode word and use prefix search. Never accept
                # raw FTS operators from the request.
                tokens = _WORDS.findall(query)[:8]
                if not tokens:
                    return {"ready": True, "items": [], "limit": limit,
                            "offset": offset, "has_more": False}
                match = " AND ".join('"' + word + '"*' for word in tokens)
                sql = (f"SELECT {columns} FROM catalog_search AS s "
                       "JOIN product_catalog AS p ON p.catalog_id=s.rowid "
                       "WHERE catalog_search MATCH ? ORDER BY p.catalog_id LIMIT ? OFFSET ?")
                params = (match, limit + 1, offset)
            else:
                sql = f"SELECT {columns} FROM product_catalog AS p ORDER BY p.catalog_id LIMIT ? OFFSET ?"
                params = (limit + 1, offset)
            rows = db.execute(sql, params).fetchall()
            items = [dict(row) for row in rows[:limit]]
            return {"ready": True, "items": items, "limit": limit,
                    "offset": offset, "has_more": len(rows) > limit}


def register_catalog_routes(app: FastAPI, db_path: str | Path) -> None:
    reader = CatalogReader(db_path)

    @app.get("/catalog", response_class=HTMLResponse)
    def catalog_page(request: Request):
        return _TEMPLATES.TemplateResponse(request, "catalog.html", {})

    @app.get("/api/catalog/stats")
    def catalog_stats() -> dict[str, object]:
        return reader.stats()

    @app.get("/api/catalog/search")
    def catalog_search(
        q: str = Query("", max_length=100),
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1_000_000),
    ) -> dict[str, object]:
        return reader.search(q, limit, offset)
