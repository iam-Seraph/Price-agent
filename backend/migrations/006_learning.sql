-- Phase 11: single-operator, explicitly enabled, reversible personalization.
-- Only structured offer feedback. No prompts, account identifiers or scraped pages.
CREATE TABLE IF NOT EXISTS verified_learning_settings (
  id INTEGER PRIMARY KEY CHECK(id=1),
  enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
  updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO verified_learning_settings(id,enabled,updated_at)
VALUES (1,0,'1970-01-01T00:00:00Z');

CREATE TABLE IF NOT EXISTS verified_offer_feedback (
  offer_id TEXT PRIMARY KEY REFERENCES verified_offers(offer_id),
  preference TEXT NOT NULL CHECK(preference IN ('PREFER','AVOID')),
  source TEXT NOT NULL DEFAULT 'USER_EXPLICIT' CHECK(source='USER_EXPLICIT'),
  updated_at TEXT NOT NULL
);
