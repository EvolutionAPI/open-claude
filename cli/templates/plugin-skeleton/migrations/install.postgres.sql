-- Install migration — PostgreSQL dialect
-- Creates the items table for the __SLUG__ plugin.

CREATE TABLE IF NOT EXISTS __SLUG_UNDER___items (
    id          SERIAL PRIMARY KEY,
    name        TEXT    NOT NULL,
    description TEXT,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
