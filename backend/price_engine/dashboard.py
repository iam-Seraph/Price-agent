"""Read-only local dashboard over the existing append-only SQLite history.

No migration, polling task, retailer HTTP call, or write endpoint is created here.
Start with: python -m price_engine.dashboard --db price_engine.sqlite3
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .tool_results import format_paisa
from .models import Paisa

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_PACKAGE = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PACKAGE / 'templates'))



def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReadOnlyHistory:
    """Opens a fresh read-only connection per call; safe for FastAPI threadpool."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def _connect(self) -> sqlite3.Connection:
        # mode=ro *never* creates the database; no mutating migrations at startup.
        if not self.path.is_file():
            raise FileNotFoundError('Database not found')
        connection = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True,
                                     timeout=3.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA query_only=ON')
            connection.execute('PRAGMA busy_timeout=2000')
            connection.execute('BEGIN')  # consistent snapshot across SELECTs
        except Exception:
            connection.close()
            raise
        return connection

    def listings(self, *, limit: int = 50, offset: int = 0, now: datetime | None = None) -> dict[str, object]:
        now = now or utc_now()
        threshold = (now - timedelta(days=30)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
        with closing(self._connect()) as db:
            rows = db.execute('''
                SELECT l.listing_id, l.retailer, l.canonical_url, l.active,
                       p.brand, p.model, p.variant,
                       h.observed_at, h.ingested_at, h.price_paisa,
                       h.availability, h.validation_status, h.source_type,
                       h.anomaly_reason
                FROM retailer_listings AS l
                JOIN products AS p ON p.product_id = l.product_id
                LEFT JOIN price_history AS h ON h.observation_id = (
                    SELECT h2.observation_id FROM price_history AS h2
                    WHERE h2.listing_id=l.listing_id
                    ORDER BY h2.observed_at DESC, h2.ingested_at DESC, h2.observation_id DESC
                    LIMIT 1
                )
                WHERE l.active=1
                ORDER BY l.created_at DESC, l.listing_id ASC
                LIMIT ? OFFSET ?
            ''', (limit, offset)).fetchall()
            items: list[dict[str, object]] = []
            for row in rows:
                if row['validation_status'] == 'QUARANTINED':
                    status = 'QUARANTINED'
                elif row['validation_status'] == 'ACCEPTED' and row['availability'] == 'OUT_OF_STOCK':
                    status = 'OUT_OF_STOCK'
                elif (row['validation_status'] == 'ACCEPTED' and
                      row['availability'] == 'IN_STOCK' and row['price_paisa'] is not None):
                    status = 'VALID_PRICE'
                else:
                    status = 'UNAVAILABLE'
                price: int | None = row['price_paisa'] if status == 'VALID_PRICE' else None
                observed_at: str | None = row['observed_at']
                observed = datetime.fromisoformat(observed_at.replace('Z', '+00:00')) if observed_at else None
                stale = observed is None or now - observed > timedelta(hours=24)
                items.append({
                    'listing_id': row['listing_id'],
                    'name': ' '.join(part for part in (row['brand'], row['model'], row['variant']) if part),
                    'retailer': row['retailer'], 'url': row['canonical_url'],
                    'status': status, 'price_paisa': price,
                    'price_display': format_paisa(Paisa(price)) if price is not None else None,
                    'stale': stale,
                    'observed_at': observed_at,
                    'source': row['source_type'],
                    'reason': row['anomaly_reason'],
                    'trend_paisa': [],
                })
            if items:
                placeholders = ','.join('?' for _ in items)
                ids = [str(item['listing_id']) for item in items]
                prices = db.execute(f'''
                    SELECT listing_id, price_paisa, observed_at FROM (
                        SELECT listing_id, price_paisa, observed_at,
                               ROW_NUMBER() OVER (
                                   PARTITION BY listing_id ORDER BY observed_at DESC, observation_id DESC
                               ) AS rn
                        FROM price_history
                        WHERE listing_id IN ({placeholders})
                          AND observed_at >= ? AND observed_at <= ?
                          AND validation_status='ACCEPTED' AND availability='IN_STOCK'
                          AND price_paisa IS NOT NULL
                    ) WHERE rn <= 60 ORDER BY listing_id, observed_at ASC
                ''', (*ids, threshold, now.isoformat(timespec='microseconds').replace('+00:00', 'Z'))).fetchall()
                grouped: dict[str, list[int]] = defaultdict(list)
                for record in prices:
                    grouped[str(record['listing_id'])].append(int(record['price_paisa']))
                for item in items:
                    item['trend_paisa'] = grouped.get(str(item['listing_id']), [])
            db.rollback()
        return {'items': items, 'limit': limit, 'offset': offset, 'generated_at': now.isoformat()}

    def history(self, listing_id: str, *, days: int = 30, now: datetime | None = None) -> dict[str, object] | None:
        now = now or utc_now()
        start = (now - timedelta(days=days)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
        end = now.isoformat(timespec='microseconds').replace('+00:00', 'Z')
        with closing(self._connect()) as db:
            exists = db.execute('SELECT 1 FROM retailer_listings WHERE listing_id=?', (listing_id,)).fetchone()
            if exists is None:
                return None
            rows = db.execute('''
                SELECT price_paisa, observed_at FROM price_history
                WHERE listing_id=? AND observed_at>=? AND observed_at<=?
                  AND validation_status='ACCEPTED' AND availability='IN_STOCK'
                  AND price_paisa IS NOT NULL
                ORDER BY observed_at ASC, observation_id ASC
                LIMIT 10000
            ''', (listing_id, start, end)).fetchall()
            db.rollback()
        points = [{'observed_at': str(row['observed_at']),
                   'price_paisa': int(row['price_paisa']),
                   'price_display': format_paisa(Paisa(int(row['price_paisa'])))} for row in rows]
        total = sum(point['price_paisa'] for point in points)
        count = len(points)
        lowest = min((point['price_paisa'] for point in points), default=None)
        # Explicit integer round-half-up; retain total/count for exact comparisons.
        avg = (2 * total + count) // (2 * count) if count else None
        return {'listing_id': listing_id, 'days': days,
                'sample_count': count, 'total_paisa': total,
                'average_paisa': avg, 'average_display': format_paisa(Paisa(avg)) if avg is not None else None,
                'low_paisa': lowest, 'low_display': format_paisa(Paisa(lowest)) if lowest is not None else None,
                'points': points}

    def health(self) -> dict[str, object]:
        with closing(self._connect()) as db:
            db.execute('SELECT 1').fetchone()
            row = db.execute('SELECT MAX(observed_at) FROM price_history').fetchone()
            db.rollback()
        return {'ok': True, 'database': 'READ_ONLY',
                'scheduler': 'NOT_CONFIGURED', 'manual_trigger_available': False,
                'last_observation_utc': row[0] if row else None}


def create_app(db_path: str | Path) -> FastAPI:
    """App factory. Sync route functions execute SQLite operations in a threadpool."""
    app = FastAPI(title='Price Agent Dashboard', docs_url=None, redoc_url=None,
                  openapi_url=None)
    store = ReadOnlyHistory(db_path)
    app.mount('/static', StaticFiles(directory=str(_PACKAGE / 'static')), name='static')

    @app.middleware('http')
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, exc: sqlite3.Error) -> JSONResponse:
        return JSONResponse(status_code=503, content={'ok': False, 'error': 'DATABASE_UNAVAILABLE'})

    @app.exception_handler(FileNotFoundError)
    async def database_missing(request: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=503, content={'ok': False, 'error': 'DATABASE_UNAVAILABLE'})

    @app.get('/', response_class=HTMLResponse)
    def homepage(request: Request) -> Response:
        return _TEMPLATES.TemplateResponse(request, 'dashboard.html', {})

    @app.get('/api/listings')
    def list_listings(limit: int = Query(50, ge=1, le=100),
                      offset: int = Query(0, ge=0, le=100000)) -> dict[str, object]:
        return store.listings(limit=limit, offset=offset)

    @app.get('/api/listings/{listing_id}/history')
    def listing_history(listing_id: str, days: int = Query(30, ge=1, le=90)) -> dict[str, object]:
        result = store.history(listing_id, days=days)
        if result is None:
            raise HTTPException(status_code=404, detail='Listing not found')
        return result

    @app.get('/api/health')
    def health() -> dict[str, object]:
        return store.health()

    from .catalog_api import register_catalog_routes
    register_catalog_routes(app, db_path)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description='Local read-only price history dashboard')
    parser.add_argument('--db', default='price_engine.sqlite3')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.db), host=args.host, port=args.port, log_level='info')


if __name__ == '__main__':
    main()
