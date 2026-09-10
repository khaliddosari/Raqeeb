"""Loads the external CLASS -> AUTHORITY -> PHONE -> ENDPOINT mapping.

This is the only place that decides which authority a detection routes to. Edit
config/authority_mapping.yaml to add/change classes or authorities -- no code change
needed.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

import yaml

from agent.config import settings
from agent.schemas import AuthorityConfig

_ENV_PATTERN = re.compile(r"\$\{(\w+)(:-(.*?))?\}")


def _expand_env(value):
    if isinstance(value, str):
        def repl(match: re.Match) -> str:
            var_name, _, default = match.groups()
            return os.environ.get(var_name, default or "")

        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


@lru_cache
def _load_raw() -> dict:
    with open(settings.authority_mapping_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _expand_env(raw)


def get_authority_for_class(detected_class: str) -> AuthorityConfig:
    raw = _load_raw()
    classes = raw.get("classes", {})
    entry = classes.get(detected_class) or raw.get("default")
    if entry is None:
        raise ValueError(f"No authority mapping (and no default) for class {detected_class!r}")
    return AuthorityConfig(**entry)


def reload_mapping() -> None:
    """Clears the cache so an edited YAML file is picked up without restarting."""
    _load_raw.cache_clear()
