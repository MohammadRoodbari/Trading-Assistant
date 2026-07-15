"""Fetch-source factory."""

from __future__ import annotations

from ..config import Config
from .interface import MarketDataSource
from .raw_source import RawSource
from .session import (
    Session,
    TsetmcBlocked,
    TsetmcError,
    TsetmcUnreachable,
)

__all__ = [
    "MarketDataSource",
    "RawSource",
    "Session",
    "TsetmcBlocked",
    "TsetmcError",
    "TsetmcUnreachable",
    "make_source",
]


def make_source(cfg: Config) -> MarketDataSource:
    if cfg.source == "library":
        from .library_source import LibrarySource

        return LibrarySource(cfg)
    return RawSource(cfg)
