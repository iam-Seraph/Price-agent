-- Additive Phase 1 migration. Does not modify legacy INR price_history tables.
-- Source provenance is PROVIDER_REPORTED, not independent merchant verification.
CREATE TABLE IF NOT EXISTS verified_offers (
    offer_id TEXT PRIMARY KEY CHECK(length(offer_id)=64),
    provider TEXT NOT NULL CHECK(provider='SERPAPI_GOOGLE_SHOPPING'),
    provider_product_id TEXT NOT NULL,
    merchant TEXT NOT NULL CHECK(length(merchant)>0),
    title TEXT NOT NULL CHECK(length(title)>0),
    product_url TEXT NOT NULL CHECK(product_url LIKE 'https://%'),
    currency TEXT NOT NULL CHECK(currency IN ('INR','USD')),
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(provider,provider_product_id,merchant,currency)
);
CREATE TABLE IF NOT EXISTS verified_offer_observations (
    event_id TEXT PRIMARY KEY CHECK(length(event_id)=32),
    offer_id TEXT NOT NULL REFERENCES verified_offers(offer_id),
    observed_at TEXT NOT NULL,
    price_minor INTEGER NOT NULL CHECK(typeof(price_minor)='integer' AND price_minor>0 AND price_minor<=1000000000000),
    stock TEXT NOT NULL CHECK(stock IN ('IN_STOCK','OUT_OF_STOCK','UNKNOWN')),
    seller_rating TEXT,
    evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
    provenance TEXT NOT NULL DEFAULT 'PROVIDER_REPORTED'
      CHECK(provenance='PROVIDER_REPORTED'),
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verified_observation_history
    ON verified_offer_observations(offer_id,observed_at DESC);
CREATE TRIGGER IF NOT EXISTS verified_history_no_update
    BEFORE UPDATE ON verified_offer_observations
    BEGIN SELECT RAISE(ABORT,'append-only verified offer observations'); END;
CREATE TRIGGER IF NOT EXISTS verified_history_no_delete
    BEFORE DELETE ON verified_offer_observations
    BEGIN SELECT RAISE(ABORT,'append-only verified offer observations'); END;
