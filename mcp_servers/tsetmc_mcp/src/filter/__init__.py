"""Custom filter feature: a safe TSETMC-flavored expression language over the snapshot."""

from __future__ import annotations

from .engine import run as run_filter
from .safe_eval import FilterError
from .variables import VARIABLE_DOCS

__all__ = ["run_filter", "FilterError", "VARIABLE_DOCS"]
