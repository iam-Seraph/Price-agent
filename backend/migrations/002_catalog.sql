-- Phase 5: independent open-data product catalog. Never fabricates retailer prices.
-- Apply only through the explicit catalog importer; leaves Phase 1 price history unchanged.
CREATE TABLE IF NOT EXISTS product_catalog (
    catalog_id INTEGER PRIMARY KEY,
    source TEXT NOT NULL CHECK(source='open_food_facts'),
    source_product_id TEXT NOT NULL,
    name TEXT NOT NULL CHECK(length(name)>0),
    brand TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    quantity TEXT NOT NULL DEFAULT '',
    countries TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL CHECK(source_url LIKE 'https://world.openfoodfacts.org/product/%'),
    last_modified_t INTEGER,
    imported_at TEXT NOT NULL,
    UNIQUE(source, source_product_id)
);
CREATE INDEX IF NOT EXISTS idx_catalog_brand ON product_catalog(brand COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_catalog_category ON product_catalog(category COLLATE NOCASE);

-- External-content FTS5: one searchable index, rather than a LIKE scan over 1M rows.
CREATE VIRTUAL TABLE IF NOT EXISTS catalog_search USING fts5(
    name, brand, category,
    content='product_catalog', content_rowid='catalog_id',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS catalog_ai AFTER INSERT ON product_catalog BEGIN
    INSERT INTO catalog_search(rowid,name,brand,category)
    VALUES(new.catalog_id,new.name,new.brand,new.category);
END;
CREATE TRIGGER IF NOT EXISTS catalog_ad AFTER DELETE ON product_catalog BEGIN
    INSERT INTO catalog_search(catalog_search,rowid,name,brand,category)
    VALUES('delete',old.catalog_id,old.name,old.brand,old.category);
END;
CREATE TRIGGER IF NOT EXISTS catalog_au AFTER UPDATE ON product_catalog BEGIN
    INSERT INTO catalog_search(catalog_search,rowid,name,brand,category)
    VALUES('delete',old.catalog_id,old.name,old.brand,old.category);
    INSERT INTO catalog_search(rowid,name,brand,category)
    VALUES(new.catalog_id,new.name,new.brand,new.category);
END;

CREATE TABLE IF NOT EXISTS catalog_import_runs (
    run_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    input_filename TEXT NOT NULL,
    max_rows INTEGER NOT NULL,
    scanned_rows INTEGER NOT NULL,
    accepted_rows INTEGER NOT NULL,
    skipped_rows INTEGER NOT NULL,
    total_products INTEGER NOT NULL,
    completed_at TEXT NOT NULL
);
