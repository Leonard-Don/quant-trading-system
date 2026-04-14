#!/usr/bin/env python3
"""Migrate SQLite fallback infrastructure data into PostgreSQL / TimescaleDB."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.persistence import PersistenceManager  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate local SQLite infra records into PostgreSQL / TimescaleDB.")
    parser.add_argument("--sqlite-path", default=None, help="Path to the SQLite source file. Defaults to the local fallback store.")
    parser.add_argument("--apply", action="store_true", help="Run the migration. Without this flag the script performs a dry-run preview.")
    parser.add_argument("--records-only", action="store_true", help="Only migrate infra_records.")
    parser.add_argument("--timeseries-only", action="store_true", help="Only migrate infra_timeseries.")
    parser.add_argument("--no-dedupe-timeseries", action="store_true", help="Insert timeseries rows even when an exact row already exists.")
    parser.add_argument("--record-limit", type=int, default=None, help="Optional limit for records to migrate.")
    parser.add_argument("--timeseries-limit", type=int, default=None, help="Optional limit for timeseries rows to migrate.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    include_records = not args.timeseries_only
    include_timeseries = not args.records_only
    if not include_records and not include_timeseries:
        parser.error("Cannot disable both records and timeseries migration.")

    manager = PersistenceManager(
        database_url=os.getenv("DATABASE_URL"),
        sqlite_path=args.sqlite_path,
    )
    result = manager.migrate_sqlite_fallback_to_postgres(
        sqlite_path=args.sqlite_path,
        dry_run=not args.apply,
        include_records=include_records,
        include_timeseries=include_timeseries,
        dedupe_timeseries=not args.no_dedupe_timeseries,
        record_limit=args.record_limit,
        timeseries_limit=args.timeseries_limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") in {"preview", "ok"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
