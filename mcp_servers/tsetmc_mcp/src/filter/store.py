"""Persistence for user-saved filters (the user's filter library).

A small JSON file in the data dir: {name: {expression, description}}. This is what
makes "create that filter and put it in the proper section" durable — Claude saves a
filter by name and the user re-runs it later.
"""

from __future__ import annotations

import json

from ..config import Config


def _path(cfg: Config):
    return cfg.data_dir / "filters.json"


def load_all(cfg: Config) -> dict[str, dict]:
    p = _path(cfg)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def get(cfg: Config, name: str) -> dict | None:
    return load_all(cfg).get(name)


def save(cfg: Config, name: str, expression: str, description: str = "") -> None:
    cfg.ensure_dirs()
    data = load_all(cfg)
    data[name] = {"expression": expression, "description": description}
    _path(cfg).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def delete(cfg: Config, name: str) -> bool:
    data = load_all(cfg)
    if name in data:
        del data[name]
        _path(cfg).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    return False
