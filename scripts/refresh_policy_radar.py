#!/usr/bin/env python3
"""
刷新 policy_radar 另类数据快照。

用途：
- 主动触发 `PolicySignalProvider.run_pipeline()`，抓取最新政策语料并跑 NLP
- 通过 `AltDataManager.refresh_provider("policy_radar")` 把信号 + 历史记录
  落盘到 `cache/alt_data/providers/policy_radar.json`
- 让 `/policy-radar/*` HTTP 端点从 `available:false` 变成 `available:true`

设计要点：
- 不依赖 Celery；与 `refresh_industry_metadata_snapshot.py` 等同款 CLI 模式
- 支持 `--force` 跳过 `needs_update()` 节流，便于 cron / 手动重跑
- 失败时 `AltDataRefreshService` 会自动回退到 `degraded` 状态并把上次快照
  原样保留，本脚本只汇总状态并返回非零 exit code

推荐 cron（每 6 小时一次）：

    0 */6 * * * cd /opt/quant-trading-system && \
        /usr/bin/env python scripts/refresh_policy_radar.py --force \
        >> logs/refresh_policy_radar.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.alternative.alt_data_manager import AltDataManager  # noqa: E402

logger = logging.getLogger("refresh_policy_radar")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def refresh_policy_radar(
    *,
    force: bool = True,
    snapshot_dir: Path | None = None,
    manager: AltDataManager | None = None,
) -> dict:
    """Run the policy_radar refresh and persist the resulting snapshot.

    Returns the refresh-status dict so callers (and tests) can assert on
    record_count / status / error without re-reading the JSON.
    """
    if manager is None:
        config: dict = {}
        if snapshot_dir is not None:
            config["snapshot_dir"] = str(snapshot_dir)
        manager = AltDataManager(config=config)

    logger.info("Starting policy_radar refresh (force=%s)", force)
    manager.refresh_provider("policy_radar", force=force)

    # Even if the provider failed, RefreshService still writes a snapshot
    # (success or degraded) plus updates refresh_status.json. We persist
    # the rolled-up dashboard snapshot too so the read endpoint sees the
    # latest envelope timestamp.
    dashboard_snapshot = manager.build_dashboard_snapshot()
    manager.snapshot_store.save_dashboard_snapshot(dashboard_snapshot)

    status = manager.refresh_status.get("policy_radar")
    status_dict = status.to_dict() if status is not None else {}

    snapshot_path = manager.snapshot_store.provider_snapshot_path("policy_radar")
    logger.info(
        "policy_radar refresh complete: status=%s record_count=%s snapshot=%s",
        status_dict.get("status"),
        status_dict.get("record_count"),
        snapshot_path,
    )
    return status_dict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh policy_radar alt-data snapshot for the HTTP endpoint",
    )
    parser.add_argument(
        "--no-force",
        action="store_true",
        help="Honor PolicySignalProvider.needs_update() throttling instead of forcing a refresh",
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=None,
        help="Override the snapshot directory (defaults to <repo>/cache/alt_data)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Emit the final refresh-status as JSON on stdout (handy for piping)",
    )
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    try:
        status = refresh_policy_radar(
            force=not args.no_force,
            snapshot_dir=args.snapshot_dir,
        )
    except Exception as exc:
        logger.exception("policy_radar refresh raised unexpectedly: %s", exc)
        return 2

    if args.print_json:
        sys.stdout.write(json.dumps(status, ensure_ascii=False, default=str) + "\n")

    return 0 if status.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
