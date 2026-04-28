-- Install migration — SQLite dialect
-- Creates the items table for the __SLUG__ plugin.

CREATE TABLE IF NOT EXISTS __SLUG_UNDER___items (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL,
    description TEXT,
    active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
