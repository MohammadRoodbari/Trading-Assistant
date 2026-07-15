"""Runtime configuration, read once from environment variables.

Every knob has a safe default so the server runs with zero configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _default_data_dir() -> Path:
    # An explicit TSETMC_DATA_DIR wins; otherwise ~/.tsetmc-mcp.
    base = os.environ.get("TSETMC_DATA_DIR")
    if base:
        return Path(base).expanduser()
    return Path.home() / ".tsetmc-mcp"


@dataclass(frozen=True)
class Config:
    # Which fetch backend serves data: "raw" (built-in aiohttp client, default,
    # runs on any Python >=3.11) or "library" (the 5j9/tsetmc accelerator, needs
    # Python >=3.13 and `pip install tsetmc`).
    source: str = os.environ.get("TSETMC_SOURCE", "raw").strip().lower()

    # Hosts (see docs/endpoints.md).
    cdn_base: str = os.environ.get("TSETMC_CDN_BASE", "https://cdn.tsetmc.com").rstrip("/")
    legacy_base: str = os.environ.get("TSETMC_LEGACY_BASE", "https://old.tsetmc.com").rstrip("/")
    members_base: str = os.environ.get("TSETMC_MEMBERS_BASE", "https://members.tsetmc.com").rstrip(
        "/"
    )

    # Polling / rate limiting.
    poll_interval_s: float = _env_float("TSETMC_POLL_INTERVAL", 5.0)
    req_per_sec: float = _env_float("TSETMC_REQ_PER_SEC", 1.5)
    max_concurrency: int = _env_int("TSETMC_MAX_CONCURRENCY", 2)
    timeout_s: float = _env_float("TSETMC_TIMEOUT", 12.0)
    retries: int = _env_int("TSETMC_RETRIES", 4)

    # Market calendar (Asia/Tehran). Continuous trading ~09:00–12:30, Sat–Wed.
    market_tz: str = os.environ.get("TSETMC_MARKET_TZ", "Asia/Tehran")
    open_hour: int = _env_int("TSETMC_OPEN_HOUR", 9)
    open_minute: int = _env_int("TSETMC_OPEN_MINUTE", 0)
    close_hour: int = _env_int("TSETMC_CLOSE_HOUR", 12)
    close_minute: int = _env_int("TSETMC_CLOSE_MINUTE", 30)

    # Output shaping defaults (protect the model's context window).
    default_limit: int = _env_int("TSETMC_DEFAULT_LIMIT", 20)
    max_limit: int = _env_int("TSETMC_MAX_LIMIT", 100)

    data_dir: Path = field(default_factory=_default_data_dir)

    @property
    def history_dir(self) -> Path:
        return self.data_dir / "history"

    @property
    def holidays_file(self) -> Path:
        # A user-maintained list of extra market holidays, one ISO date (YYYY-MM-DD,
        # Gregorian) per line. Blank lines and lines starting with '#' are ignored.
        return self.data_dir / "holidays.txt"

    def ensure_dirs(self) -> None:
        self.history_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    return Config()
