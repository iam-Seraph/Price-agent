PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS products (
 product_id TEXT PRIMARY KEY,
 brand TEXT NOT NULL,
 model TEXT NOT NULL,
 variant TEXT NOT NULL DEFAULT '',
 gtin TEXT UNIQUE,
 created_at TEXT NOT NULL CHECK(created_at GLOB '????-??-??T*Z')
);
CREATE TABLE IF NOT EXISTS retailer_listings (
 listing_id TEXT PRIMARY KEY,
 product_id TEXT REFERENCES products(product_id) NOT NULL,
 retailer TEXT NOT NULL,
 retailer_product_id TEXT NOT NULL,
 seller_id TEXT NOT NULL DEFAULT '',
 canonical_url TEXT NOT NULL CHECK(canonical_url LIKE 'https://%'),
 currency TEXT NOT NULL DEFAULT 'INR' CHECK(currency='INR'),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 created_at TEXT NOT NULL CHECK(created_at GLOB '????-??-??T*Z'),
 UNIQUE(retailer,retailer_product_id,seller_id)
);
CREATE INDEX IF NOT EXISTS idx_listings_product ON retailer_listings(product_id);
CREATE TABLE IF NOT EXISTS price_history (
 observation_id TEXT PRIMARY KEY,
 listing_id TEXT NOT NULL REFERENCES retailer_listings(listing_id),
 observed_at TEXT NOT NULL CHECK(observed_at GLOB '????-??-??T*Z'),
 ingested_at TEXT NOT NULL CHECK(ingested_at GLOB '????-??-??T*Z'),
 price_paisa INTEGER CHECK(price_paisa IS NULL OR (typeof(price_paisa)='integer' AND price_paisa>0)),
 availability TEXT NOT NULL CHECK(availability IN ('IN_STOCK','OUT_OF_STOCK','UNKNOWN')),
 source_type TEXT NOT NULL CHECK(source_type IN ('API','HTML')),
 extraction_version TEXT NOT NULL,
 source_record_id TEXT NOT NULL,
 raw_payload_hash TEXT NOT NULL,
 validation_status TEXT NOT NULL CHECK(validation_status IN ('ACCEPTED','QUARANTINED')),
 anomaly_reason TEXT,
 CHECK(validation_status!='ACCEPTED' OR (
   (availability='IN_STOCK' AND price_paisa IS NOT NULL) OR
   (availability='OUT_OF_STOCK' AND price_paisa IS NULL)
 )),
 UNIQUE(listing_id,source_type,source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_history_listing_time ON price_history(listing_id,observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_accepted ON price_history(listing_id,observed_at DESC) WHERE validation_status='ACCEPTED' AND price_paisa IS NOT NULL;
CREATE TABLE IF NOT EXISTS ingestion_attempts (
 attempt_id TEXT PRIMARY KEY,
 listing_id TEXT NOT NULL REFERENCES retailer_listings(listing_id),
 source_type TEXT NOT NULL CHECK(source_type IN ('API','HTML')),
 status TEXT NOT NULL,
 attempted_at TEXT NOT NULL,
 retry_after_seconds INTEGER,
 error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_attempts_listing_time ON ingestion_attempts(listing_id,attempted_at DESC);
CREATE TRIGGER IF NOT EXISTS history_no_update BEFORE UPDATE ON price_history BEGIN SELECT RAISE(ABORT,'append-only history'); END;
CREATE TRIGGER IF NOT EXISTS history_no_delete BEFORE DELETE ON price_history BEGIN SELECT RAISE(ABORT,'append-only history'); END;
