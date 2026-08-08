-- Crypto payments D1 schema.
-- Apply with: wrangler d1 execute crypto-payments --file workers/schema.sql
--
-- Security notes (crypto-rules.yaml):
--  - payments.tx_hash is the PRIMARY KEY: replay protection.
--  - delivery tokens are one-time use with expiry.
--  - donation_addresses store PUBLIC addresses only.

CREATE TABLE IF NOT EXISTS resources (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  price_usdc REAL NOT NULL DEFAULT 0,
  resource_path TEXT NOT NULL,
  checksum TEXT NOT NULL DEFAULT '',
  version TEXT NOT NULL DEFAULT '1.0',
  free INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payments (
  tx_hash TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL,
  payer TEXT NOT NULL DEFAULT '',
  token TEXT NOT NULL DEFAULT 'USDC',
  amount TEXT NOT NULL DEFAULT '',
  network TEXT NOT NULL DEFAULT 'polygon',
  status TEXT NOT NULL DEFAULT 'pending',
  verified_at TEXT,
  delivery_token TEXT
);

CREATE TABLE IF NOT EXISTS delivery_tokens (
  token TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL,
  resource_path TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0,
  used_at TEXT
);

CREATE TABLE IF NOT EXISTS donation_addresses (
  network TEXT NOT NULL,
  token TEXT NOT NULL,
  address TEXT NOT NULL,
  PRIMARY KEY (network, token)
);

CREATE TABLE IF NOT EXISTS rate_limits (
  key TEXT PRIMARY KEY,
  count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_payments_resource ON payments (resource_id);
CREATE INDEX IF NOT EXISTS idx_delivery_resource ON delivery_tokens (resource_id);
