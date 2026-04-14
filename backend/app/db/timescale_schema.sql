-- Quant system PostgreSQL + TimescaleDB schema.
-- Run this on the production database referenced by DATABASE_URL.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS market_timeseries (
    symbol TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown',
    ts TIMESTAMPTZ NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, provider, ts)
);

SELECT create_hypertable('market_timeseries', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS research_tasks (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    owner_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS strategy_config_versions (
    id TEXT PRIMARY KEY,
    owner_id TEXT,
    config_type TEXT NOT NULL,
    config_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, config_type, config_key, version)
);

CREATE TABLE IF NOT EXISTS alert_events (
    id BIGSERIAL PRIMARY KEY,
    owner_id TEXT,
    source_module TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    event_key TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

SELECT create_hypertable('alert_events', 'triggered_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS valuation_snapshots (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    owner_id TEXT,
    fair_value NUMERIC,
    market_price NUMERIC,
    gap_pct NUMERIC,
    confidence_low NUMERIC,
    confidence_high NUMERIC,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

SELECT create_hypertable('valuation_snapshots', 'created_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS data_quality_events (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms NUMERIC,
    freshness_minutes NUMERIC,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

SELECT create_hypertable('data_quality_events', 'checked_at', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_market_timeseries_symbol_ts
    ON market_timeseries (symbol, ts DESC);

CREATE INDEX IF NOT EXISTS idx_research_tasks_owner_status
    ON research_tasks (owner_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_strategy_config_versions_lookup
    ON strategy_config_versions (owner_id, config_type, config_key, version DESC);

CREATE INDEX IF NOT EXISTS idx_alert_events_owner_time
    ON alert_events (owner_id, triggered_at DESC);

CREATE INDEX IF NOT EXISTS idx_valuation_snapshots_symbol_time
    ON valuation_snapshots (symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_data_quality_events_provider_time
    ON data_quality_events (provider, checked_at DESC);
