-- Opt-in local price-watch scheduling, separate from legacy history and demos.
CREATE TABLE IF NOT EXISTS verified_watch_queries (
  watch_id TEXT PRIMARY KEY CHECK(length(watch_id)=32),
  query_text TEXT NOT NULL CHECK(length(query_text) BETWEEN 2 AND 120),
  currency TEXT NOT NULL CHECK(currency IN ('INR','USD')),
  budget_minor INTEGER NOT NULL CHECK(budget_minor>0),
  interval_seconds INTEGER NOT NULL CHECK(interval_seconds BETWEEN 900 AND 86400),
  enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
  created_at TEXT NOT NULL,
  next_due_at TEXT NOT NULL,
  last_checked_at TEXT,
  last_status TEXT,
  lease_owner TEXT,
  lease_expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_watch_due ON verified_watch_queries(enabled,next_due_at);
CREATE TABLE IF NOT EXISTS verified_watch_runs (
  run_id TEXT PRIMARY KEY CHECK(length(run_id)=32),
  watch_id TEXT NOT NULL REFERENCES verified_watch_queries(watch_id),
  started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('OK','NO_MATCHES','PROVIDER_UNAVAILABLE','ERROR')),
  offers_inspected INTEGER NOT NULL CHECK(offers_inspected>=0),
  inserted_observations INTEGER NOT NULL CHECK(inserted_observations>=0),
  message TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_watch_runs ON verified_watch_runs(watch_id,completed_at DESC);
