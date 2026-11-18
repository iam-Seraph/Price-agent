"""Stream the official Open Food Facts TSV/CSV export into indexed SQLite.

This module never generates products/prices or contacts retailers. The user must
download an OFF bulk export separately and supply a local path explicitly.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

SOURCE = "open_food_facts"
SCHEMA = Path(__file__).resolve().parents[1] / "migrations" / "002_catalog.sql"
UPC = re.compile(r"[0-9]{8,14}\Z")
# Exclude age-restricted/intoxicating categories from the public-facing catalog.
_RESTRICTED = re.compile(
    r"\b(?:alcoholic[-\s]beverages?|beers?|wines?|spirits?|liquors?|liqueurs?|" 
    r"ciders?|champagnes?|whisk(?:e)?y|vodka|tequila|tobacco|nicotine)\b",
    re.IGNORECASE,
)

WRITE_SQL = """
INSERT INTO product_catalog
(source,source_product_id,name,brand,category,quantity,countries,
 source_url,last_modified_t,imported_at)
VALUES (?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(source,source_product_id) DO UPDATE SET
 name=excluded.name,brand=excluded.brand,category=excluded.category,
 quantity=excluded.quantity,countries=excluded.countries,
 source_url=excluded.source_url,last_modified_t=excluded.last_modified_t,
 imported_at=excluded.imported_at
WHERE product_catalog.name IS NOT excluded.name
   OR product_catalog.brand IS NOT excluded.brand
   OR product_catalog.category IS NOT excluded.category
   OR product_catalog.quantity IS NOT excluded.quantity
   OR product_catalog.countries IS NOT excluded.countries
   OR product_catalog.last_modified_t IS NOT excluded.last_modified_t
"""


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean(value: str | None, limit: int) -> str:
    return (value or "").replace("\x00", "").strip()[:limit]


def normalize(row: dict[str, str | None], imported_at: str) -> tuple[object, ...] | None:
    """Only identifiable records with a non-empty product name are imported."""
    code = clean(row.get("code") or row.get("barcode"), 32)
    name = clean(row.get("product_name"), 300)
    if not UPC.fullmatch(code) or not name:
        return None
    classification = " ".join(clean(row.get(key), 1200) for key in
                              ("categories", "categories_tags", "main_category", "product_name"))
    if _RESTRICTED.search(classification):
        return None
    modified = clean(row.get("last_modified_t"), 24)
    modified_t = int(modified) if modified.isdigit() else None
    return (
        SOURCE, code, name, clean(row.get("brands") or row.get("brand"), 160),
        clean(row.get("main_category") or row.get("categories"), 240),
        clean(row.get("quantity"), 80), clean(row.get("countries"), 160),
        "https://world.openfoodfacts.org/product/" + code,
        modified_t, imported_at,
    )


def read_rows(handle: TextIO):
    first_line = handle.readline()
    if not first_line:
        raise ValueError("Empty input export")
    delimiter = "\t" if "\t" in first_line else ","
    handle.seek(0)
    reader = csv.DictReader(handle, delimiter=delimiter)
    headers = set(reader.fieldnames or [])
    if not ({"code", "barcode"} & headers) or "product_name" not in headers:
        raise ValueError("Expected Open Food Facts export headers: code, product_name")
    yield from reader


def import_catalog(
    input_path: str | Path,
    db_path: str | Path,
    *,
    max_rows: int = 1_000_000,
    batch_size: int = 2000,
    report_every: int = 50000,
) -> dict[str, object]:
    if max_rows < 1 or not 1 <= batch_size <= 10000 or report_every < 1:
        raise ValueError("Invalid max_rows, batch_size or report_every")
    source_path = Path(input_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    database_path = Path(db_path).expanduser().resolve()
    if source_path == database_path:
        raise ValueError("Input export and SQLite database must be different files")

    scanned = accepted = skipped = 0
    run_id = uuid.uuid4().hex
    imported_at = timestamp()
    batch: list[tuple[object, ...]] = []
    csv.field_size_limit(10_000_000)

    db = sqlite3.connect(database_path, timeout=30)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA.read_text(encoding="utf-8"))
        open_file = gzip.open if source_path.suffix.lower() == ".gz" else open
        with open_file(source_path, mode="rt", encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row in read_rows(handle):
                scanned += 1
                product = normalize(row, imported_at)
                if product is None:
                    skipped += 1
                    continue
                batch.append(product)
                accepted += 1
                if len(batch) >= batch_size:
                    with db:
                        db.executemany(WRITE_SQL, batch)
                    batch.clear()
                    if accepted % report_every < batch_size:
                        print(f"Imported rows processed: {accepted:,} | scanned: {scanned:,}", flush=True)
                if accepted >= max_rows:
                    break
        if batch:
            with db:
                db.executemany(WRITE_SQL, batch)

        total = int(db.execute("SELECT COUNT(*) FROM product_catalog").fetchone()[0])
        with db:
            db.execute("""
                INSERT INTO catalog_import_runs
                (run_id,source,input_filename,max_rows,scanned_rows,accepted_rows,
                 skipped_rows,total_products,completed_at)
                VALUES(?,?,?,?,?,?,?,?,?)
            """, (run_id, SOURCE, source_path.name, max_rows, scanned, accepted,
                  skipped, total, timestamp()))
        return {
            "source": SOURCE, "run_id": run_id, "scanned_rows": scanned,
            "accepted_rows": accepted, "skipped_rows": skipped,
            "catalog_products": total, "target": max_rows,
            "prices_imported": 0, "database": str(database_path),
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import real OFF products into local SQLite")
    parser.add_argument("--input", required=True, help="Downloaded OFF .csv/.tsv or .gz file")
    parser.add_argument("--db", default="price_engine.sqlite3", help="SQLite output DB")
    parser.add_argument("--max-rows", type=int, default=1_000_000)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--report-every", type=int, default=50000)
    args = parser.parse_args()
    result = import_catalog(args.input, args.db, max_rows=args.max_rows,
                            batch_size=args.batch_size, report_every=args.report_every)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
