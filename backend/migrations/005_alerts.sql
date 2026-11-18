-- Opt-in alert channels, transactional queue and delivery receipts.
-- No email addresses, chat IDs, bot tokens, API keys or passwords stored here.
CREATE TABLE IF NOT EXISTS verified_alert_rules (
  rule_id TEXT PRIMARY KEY CHECK(length(rule_id)=32),
  watch_id TEXT NOT NULL REFERENCES verified_watch_queries(watch_id),
  channel TEXT NOT NULL CHECK(channel IN ('EMAIL','TELEGRAM')),
  enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
  created_at TEXT NOT NULL,
  UNIQUE(watch_id,channel)
);
CREATE TABLE IF NOT EXISTS verified_alert_outbox (
  delivery_id TEXT PRIMARY KEY CHECK(length(delivery_id)=32),
  watch_id TEXT NOT NULL REFERENCES verified_watch_queries(watch_id),
  offer_id TEXT NOT NULL REFERENCES verified_offers(offer_id),
  channel TEXT NOT NULL CHECK(channel IN ('EMAIL','TELEGRAM')),
  observed_day TEXT NOT NULL CHECK(length(observed_day)=10),
  price_minor INTEGER NOT NULL CHECK(price_minor>0),
  currency TEXT NOT NULL CHECK(currency IN ('INR','USD')),
  created_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('QUEUED','LEASED','DELIVERED','FAILED')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
  next_attempt_at TEXT NOT NULL,
  lease_owner TEXT,
  lease_expires_at TEXT,
  delivered_at TEXT,
  last_error TEXT NOT NULL DEFAULT '',
  UNIQUE(watch_id,offer_id,channel,observed_day)
);
CREATE INDEX IF NOT EXISTS idx_alert_outbox_due
  ON verified_alert_outbox(status,next_attempt_at,lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_alert_outbox_watch
  ON verified_alert_outbox(watch_id,created_at DESC);
