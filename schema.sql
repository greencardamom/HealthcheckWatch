CREATE TABLE IF NOT EXISTS monitors (
  id TEXT PRIMARY KEY,
  last_ping INTEGER NOT NULL,
  timeout_hours INTEGER DEFAULT 13,
  alert_subject TEXT,
  alert_body TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject TEXT NOT NULL,
  body TEXT NOT NULL
);
