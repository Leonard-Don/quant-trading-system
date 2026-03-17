"""
另类数据 runtime：共享 manager 与 scheduler。
"""

from __future__ import annotations

from typing import Optional

from .alt_data_manager import AltDataManager
from .governance import AltDataScheduler

_manager: Optional[AltDataManager] = None
_scheduler: Optional[AltDataScheduler] = None


def get_alt_data_manager() -> AltDataManager:
    global _manager
    if _manager is None:
        _manager = AltDataManager()
    return _manager


def get_alt_data_scheduler() -> AltDataScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AltDataScheduler(get_alt_data_manager())
    return _scheduler


def start_alt_data_scheduler() -> AltDataScheduler:
    scheduler = get_alt_data_scheduler()
    scheduler.start()
    return scheduler


def stop_alt_data_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
