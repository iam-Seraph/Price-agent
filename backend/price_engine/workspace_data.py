"""Isolated, local-only workspace datasets. Never writes to price_history."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
MAX_SCAN_ROWS = 2000
MAX_COLUMNS = 32
MAX_EXCEL_UNCOMPRESSED = 15 * 1024 * 1024
PACKAGE = Path(__file__).resolve().parent
DEMO_PATH = PACKAGE / "data" / "demo_products.json"


def _text(value: Any, field: str, limit: int, *, required: bool = False) -> str:
    result = str(value).strip() if value is not None else ""
    if required and not result:
        raise ValueError(f"{field} is required")
    if len(result) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return result


def _specs(value: Any) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("specs must be a JSON object") from exc
    if not isinstance(value, dict) or len(value) > 20:
        raise ValueError("specs must be an object with up to 20 entries")
    return {_text(k, "spec key", 50, required=True): _text(v, "spec value", 200)
            for k, v in value.items()}


def normalize(row: dict[str, Any], index: int) -> dict[str, Any]:
    """Prices are INR rupees in input, stored as exact integer paisa."""
    if not isinstance(row, dict):
        raise ValueError(f"Row {index}: expected an object")
    try:
        name = _text(row.get("name"), "name", 180, required=True)
        retailer = _text(row.get("retailer"), "retailer", 100, required=True)
        currency = _text(row.get("currency") or "INR", "currency", 3).upper()
        if currency != "INR":
            raise ValueError("only INR uploads are supported")
        raw_price = row.get("price")
        if raw_price is None or isinstance(raw_price, bool):
            raise ValueError("price must be a number in INR rupees")
        try:
            price = Decimal(str(raw_price).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("price must be a decimal number") from exc
        if not price.is_finite() or not 0 <= price <= Decimal("10000000"):
            raise ValueError("price must be finite and between 0 and 10000000")
        if price.as_tuple().exponent < -2 and price != price.quantize(Decimal("0.01")):
            raise ValueError("price cannot have more than two decimal places")
        paisa = int((price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        availability = _text(row.get("availability") or "UNKNOWN", "availability", 20).upper()
        if availability not in {"IN_STOCK", "OUT_OF_STOCK", "UNKNOWN"}:
            raise ValueError("availability must be IN_STOCK, OUT_OF_STOCK or UNKNOWN")
        rating_raw = row.get("rating")
        rating = None
        if rating_raw not in (None, ""):
            if isinstance(rating_raw, bool):
                raise ValueError("rating must be between 0 and 5")
            rating = float(rating_raw)
            if not 0 <= rating <= 5:
                raise ValueError("rating must be between 0 and 5")
        count_raw = row.get("review_count")
        reviews = None
        if count_raw not in (None, ""):
            if isinstance(count_raw, bool) or not str(count_raw).isdigit():
                raise ValueError("review_count must be a nonnegative integer")
            reviews = int(count_raw)
            if reviews > 10_000_000:
                raise ValueError("review_count is too large")
        url = _text(row.get("product_url"), "product_url", 500)
        if url:
            parts = urlsplit(url)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
                raise ValueError("product_url must be a public HTTPS URL")
        return {"name": name, "retailer": retailer, "currency": "INR",
                "price_paisa": paisa, "price_display": f"₹{paisa // 100:,}.{paisa % 100:02d}",
                "availability": availability, "rating": rating, "review_count": reviews,
                "specs": _specs(row.get("specs")), "product_url": url or None}
    except (ValueError, TypeError, OverflowError, InvalidOperation) as exc:
        raise ValueError(f"Row {index}: {exc}") from exc


def normalize_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError(f"Dataset must contain 1–{MAX_ROWS} product rows")
    return [normalize(row, i) for i, row in enumerate(rows, start=1)]


def parse_upload(filename: str, content: bytes) -> list[dict[str, Any]]:
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("File must be nonempty and at most 2 MB")
    extension = Path(filename).suffix.lower()
    if extension not in {".csv", ".json", ".xlsx"}:
        raise ValueError("Only .csv, .json and .xlsx files are accepted")
    try:
        if extension == ".json":
            data = json.loads(content.decode("utf-8-sig"))
            rows = data.get("products") if isinstance(data, dict) else data
        elif extension == ".csv":
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            if (not reader.fieldnames or len(reader.fieldnames) > MAX_COLUMNS
                    or any(not field or not field.strip() for field in reader.fieldnames)
                    or len(set(reader.fieldnames)) != len(reader.fieldnames)):
                raise ValueError("CSV requires unique nonempty headers (maximum 32)")
            rows = []
            for scanned, row in enumerate(reader, start=1):
                if scanned > MAX_SCAN_ROWS:
                    raise ValueError("Too many CSV records (including blank rows)")
                if len(rows) >= MAX_ROWS:
                    raise ValueError(f"Maximum {MAX_ROWS} rows allowed")
                if None in row:
                    raise ValueError("CSV row has more fields than its header")
                if any(v not in (None, "") for v in row.values()):
                    rows.append(row)
        else:
            from openpyxl import load_workbook
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if len(archive.infolist()) > 100 or sum(
                    entry.file_size for entry in archive.infolist()
                ) > MAX_EXCEL_UNCOMPRESSED:
                    raise ValueError("Excel workbook exceeds decompression limits")
            try:
                workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            except (ValueError, TypeError, IndexError, AttributeError) as exc:
                raise ValueError("Invalid Excel workbook") from exc
            try:
                iterator = workbook.active.iter_rows(values_only=True)
                headers = [str(x).strip() if x is not None else "" for x in next(iterator)]
                if (not headers or len(headers) > MAX_COLUMNS
                        or len(set(headers)) != len(headers) or not all(headers)):
                    raise ValueError("Excel requires unique, nonempty headers (maximum 32)")
                rows = []
                for scanned, values in enumerate(iterator, start=1):
                    if scanned > MAX_SCAN_ROWS:
                        raise ValueError("Too many Excel records (including blank rows)")
                    if all(value is None for value in values):
                        continue
                    if len(rows) >= MAX_ROWS:
                        raise ValueError(f"Maximum {MAX_ROWS} rows allowed")
                    if len(values) > len(headers) and any(v is not None for v in values[len(headers):]):
                        raise ValueError("Excel row contains unnamed columns")
                    rows.append(dict(zip(headers, values)))
            finally:
                workbook.close()
        return normalize_rows(rows)
    except (UnicodeError, json.JSONDecodeError, csv.Error, zipfile.BadZipFile,
            zipfile.LargeZipFile, KeyError, StopIteration, OSError) as exc:
        raise ValueError(f"Invalid {extension} file") from exc


class WorkspaceStore:
    """Demo and uploaded rows are isolated from the append-only price engine."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=5000")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _replace(db: sqlite3.Connection, source: str, rows: list[dict[str, Any]]) -> None:
        db.execute("DELETE FROM dataset_rows WHERE source=?", (source,))
        db.executemany("INSERT INTO dataset_rows(source,row_id,name,retailer,payload) VALUES(?,?,?,?,?)",
                       [(source, i, r["name"], r["retailer"], json.dumps(r))
                        for i, r in enumerate(rows, 1)])

    def _initialize(self) -> None:
        demo = normalize_rows(json.loads(DEMO_PATH.read_text(encoding="utf-8")))
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS dataset_rows (
                    source TEXT NOT NULL CHECK(source IN ('demo','upload')),
                    row_id INTEGER NOT NULL, name TEXT NOT NULL,
                    retailer TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(source,row_id)
                );
                CREATE TABLE IF NOT EXISTS workspace_settings (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
            """)
            if not db.execute("SELECT 1 FROM dataset_rows WHERE source='demo' LIMIT 1").fetchone():
                self._replace(db, "demo", demo)
            db.execute("INSERT OR IGNORE INTO workspace_settings(key,value) VALUES('active','demo')")

    def activate(self, source: str) -> dict[str, Any]:
        if source not in {"demo", "upload"}:
            raise ValueError("Invalid dataset source")
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM dataset_rows WHERE source=? LIMIT 1", (source,)).fetchone():
                raise ValueError("Upload a dataset before activating it")
            db.execute("UPDATE workspace_settings SET value=? WHERE key='active'", (source,))
        return self.stats()

    def load_demo(self) -> dict[str, Any]:
        demo = normalize_rows(json.loads(DEMO_PATH.read_text(encoding="utf-8")))
        with self._connect() as db:
            self._replace(db, "demo", demo)
            db.execute("UPDATE workspace_settings SET value='demo' WHERE key='active'")
        return self.stats()

    def save_upload(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        with self._connect() as db:
            self._replace(db, "upload", rows)
            db.execute("UPDATE workspace_settings SET value='upload' WHERE key='active'")
        return self.stats()

    def stats(self) -> dict[str, Any]:
        with self._connect() as db:
            active = db.execute("SELECT value FROM workspace_settings WHERE key='active'").fetchone()[0]
            counts = {r["source"]: r["count"] for r in db.execute(
                "SELECT source, COUNT(*) AS count FROM dataset_rows GROUP BY source")}
        return {"active": active, "counts": {"demo": counts.get("demo", 0),
                                                "upload": counts.get("upload", 0)}}

    def products(self, query: str = "", limit: int = 100, offset: int = 0) -> dict[str, Any]:
        # Read active selection and its rows using one snapshot; switching
        # the source during a request must not mix two datasets.
        q = query.casefold()
        with self._connect() as db:
            db.execute("BEGIN")
            active = db.execute(
                "SELECT value FROM workspace_settings WHERE key='active'"
            ).fetchone()[0]
            rows = db.execute("SELECT payload FROM dataset_rows WHERE source=? ORDER BY row_id",
                              (active,)).fetchall()
        matched = [json.loads(r["payload"]) for r in rows]
        if q:
            matched = [r for r in matched if q in (r["name"] + " " + r["retailer"]).casefold()]
        return {"source": active, "total": len(matched),
                "items": matched[offset:offset + limit], "limit": limit, "offset": offset,
                "provenance": "SYNTHETIC_DEMO" if active == "demo" else "USER_UPLOADED"}
