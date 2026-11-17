"""End-to-end offline demonstration: fixture HTML -> validation -> SQLite."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
from .adapters import Listing
from .live_html import StructuredHTMLClient
from .storage import PriceStore
from .validation import validate_observation

def main() -> None:
    parser = argparse.ArgumentParser(description='Offline verified fixture ingestion')
    parser.add_argument('--db', default='price_engine.sqlite3')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    store = PriceStore(args.db, root / 'migrations' / '001_initial.sql')
    listing = Listing('demo-croma-sku123', 'croma', 'SKU123', 'https://www.croma.com/example', 'demo-product')
    now = datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    with store.connection:
        store.connection.execute('INSERT OR IGNORE INTO products(product_id,brand,model,created_at) VALUES(?,?,?,?)', ('demo-product','Demo','Fixture Headphones',now))
        store.connection.execute('INSERT OR IGNORE INTO retailer_listings(listing_id,product_id,retailer,retailer_product_id,canonical_url,created_at) VALUES(?,?,?,?,?,?)', (listing.listing_id, listing.product_id, listing.retailer, listing.retailer_product_id, listing.canonical_url, now))
    html = (root / 'tests' / 'fixtures' / 'croma_product.html').read_text(encoding='utf-8')
    adapter = StructuredHTMLClient(allowed_domains=('croma.com',))
    observation = adapter.parse(listing, html, 'fixture-2026-11-17-v1')
    verified = validate_observation(observation, store.accepted_prices(listing.listing_id))
    inserted = store.persist(verified)
    print(f'Status: {verified.status.value}; price_paisa: {verified.price_paisa}; inserted: {inserted}; database: {args.db}')
    store.close()

if __name__ == '__main__':
    main()
