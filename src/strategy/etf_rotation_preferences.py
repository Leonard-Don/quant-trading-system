"""Per-installation UI preference store for the ETF rotation dashboard.

Why this exists
---------------

The strategy config (``strategy.json``) is the system-of-record for things
that affect headless / cron / CI runs. But the dashboard also needs a way
for a logged-in human to flip ergonomic feature switches (currently just
``policy_signal_factor_enabled``) without editing JSON files or
restarting anything.

So we keep a small JSON file at ``~/.config/etf-rotation/ui_preferences.json``
(or ``ETF_PREFERENCES_PATH`` if the env var is set). The file is written
atomically (write-then-rename) so a half-flushed write can never corrupt
the runtime view. Reads tolerate a missing or invalid file by returning
an empty preference set, which lets the rest of the system fall back to
the config defaults.

Precedence (highest wins)
-------------------------

1. Explicit per-call argument (CLI flag, API query param).
2. UI preference loaded from this file.
3. ``strategy.json`` → ``strategy.policy_signal_factor_enabled``.
4. Built-in default (currently ``False``).

The store is intentionally tiny — a single ``Mapping[str, Any]`` keyed by
preference name. Adding a new preference is a matter of:

* documenting the key in ``KNOWN_PREFERENCES``;
* threading it through ``EtfRotationPreferences.effective_*`` resolvers
  or the API endpoints that consume it.

There is no schema migration story yet because there are no fields to
migrate; unknown keys are passed through verbatim so a forward-compatible
frontend can roundtrip new fields without backend changes.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


PREFERENCES_PATH_ENV = "ETF_PREFERENCES_PATH"
DEFAULT_PREFERENCES_PATH = (
    Path.home() / ".config" / "etf-rotation" / "ui_preferences.json"
)

# Known preference keys with their (type, default) tuple. ``default`` is
# the value returned by ``EtfRotationPreferences.get`` when the key is
# absent from the preferences file. Unknown keys remain accessible via
# ``raw()`` but do not get a typed accessor.
KNOWN_PREFERENCES: dict[str, dict[str, Any]] = {
    "policy_signal_factor_enabled": {
        "type": bool,
        # ``None`` means "no opinion" — caller should fall through to the
        # config-file default. We store ``True``/``False``/``None`` so the
        # UI can distinguish "user hasn't touched it" from "user turned it
        # off explicitly".
        "default": None,
    },
}


def _resolve_path(explicit: Optional[Path] = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    env_value = os.environ.get(PREFERENCES_PATH_ENV)
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_PREFERENCES_PATH


def _coerce_bool(value: Any) -> Optional[bool]:
    """Best-effort bool parser used when reading the prefs file.

    JSON booleans survive round-trip, but humans editing the file by hand
    sometimes write ``"true"``/``"false"`` as strings. We tolerate both,
    and treat any other value as "no preference" rather than blowing up.
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return None


@dataclass(frozen=True)
class PreferenceSnapshot:
    """Plain-data view of the current preference file, safe to serialise."""

    policy_signal_factor_enabled: Optional[bool]
    raw: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe representation for API responses."""

        return {
            "policy_signal_factor_enabled": self.policy_signal_factor_enabled,
        }


class EtfRotationPreferences:
    """Thread-safe reader/writer for the ETF rotation UI preferences file.

    The default singleton lives at module level (``get_preferences_store``).
    Tests typically construct a temporary instance pointed at a ``tmp_path``
    so they get isolation without monkeypatching globals.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = _resolve_path(path)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def _read_raw(self) -> dict[str, Any]:
        path = self._path
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to read ETF preferences from %s (%s); using defaults.",
                path,
                exc,
            )
            return {}
        if not isinstance(data, Mapping):
            logger.warning(
                "ETF preferences file %s is not a JSON object; ignoring.",
                path,
            )
            return {}
        return dict(data)

    def snapshot(self) -> PreferenceSnapshot:
        """Read the current preferences as a typed snapshot."""

        with self._lock:
            raw = self._read_raw()
        return PreferenceSnapshot(
            policy_signal_factor_enabled=_coerce_bool(
                raw.get("policy_signal_factor_enabled")
            ),
            raw=raw,
        )

    def update(self, patch: Mapping[str, Any]) -> PreferenceSnapshot:
        """Merge ``patch`` into the existing preferences and persist atomically.

        Keys with the value ``None`` are *removed* from the store, so the
        caller can clear an opinion without leaving an explicit ``null``
        sitting in the file forever.
        """

        with self._lock:
            current = self._read_raw()
            for key, value in patch.items():
                if value is None:
                    current.pop(key, None)
                else:
                    current[key] = value
            self._atomic_write(current)
        return self.snapshot()

    def clear(self) -> PreferenceSnapshot:
        """Remove the entire preferences file. Mostly used by tests."""

        with self._lock, contextlib.suppress(FileNotFoundError):
            self._path.unlink()
        return self.snapshot()

    def _atomic_write(self, payload: Mapping[str, Any]) -> None:
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        # Same temp-file + rename pattern as ``governance.AltDataCacheStore``
        # — guarantees that any concurrent reader either sees the old
        # bytes or the new ones, never a half-written object.
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        temp_path.replace(path)

    def resolve_policy_signal_factor_enabled(
        self,
        *,
        explicit: Optional[bool],
        config_default: bool,
    ) -> bool:
        """Resolve the effective ``policy_signal_factor_enabled`` flag.

        Precedence: ``explicit`` > preference file > ``config_default``.
        """

        if explicit is not None:
            return bool(explicit)
        snap = self.snapshot()
        if snap.policy_signal_factor_enabled is not None:
            return bool(snap.policy_signal_factor_enabled)
        return bool(config_default)


# Module-level singleton — built lazily so tests can override the env var
# before any code touches the disk.
_default_store: Optional[EtfRotationPreferences] = None
_default_store_lock = threading.Lock()


def get_preferences_store() -> EtfRotationPreferences:
    """Return the process-wide preferences store (lazy singleton)."""

    global _default_store
    if _default_store is None:
        with _default_store_lock:
            if _default_store is None:
                _default_store = EtfRotationPreferences()
    return _default_store


def reset_preferences_store_for_tests() -> None:
    """Drop the cached singleton so the next ``get_preferences_store`` call
    re-resolves the path from the env var. Tests use this to isolate
    state — production code never needs to call it."""

    global _default_store
    with _default_store_lock:
        _default_store = None


__all__ = [
    "DEFAULT_PREFERENCES_PATH",
    "KNOWN_PREFERENCES",
    "PREFERENCES_PATH_ENV",
    "EtfRotationPreferences",
    "PreferenceSnapshot",
    "get_preferences_store",
    "reset_preferences_store_for_tests",
]
