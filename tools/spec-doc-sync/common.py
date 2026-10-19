"""Shared helpers for the spec-doc-sync tooling."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parents[1]
CACHE_DIR = TOOL_DIR / ".cache"
SNAPSHOT_DIR = TOOL_DIR / ".snapshots"
MAPPING_DIR = TOOL_DIR / "mapping"

DOC_BASE_URL = "https://ipgeolocation.io/documentation"
DEFAULT_SLUGS = [
    "ip-location-api",
    "ip-security-api",
    "asn-api",
    "ip-abuse-contact-api",
    "timezone-api",
    "user-agent-api",
    "astronomy-api",
]


def ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def load_structured(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def resolve_repo_path(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else REPO_ROOT / p


def canon_type(raw):
    """Canonicalize a type token from docs/spec/JSON so equivalents compare equal.

    Docs use: string, boolean, float, number, array, array[string], enum.
    Specs use: string, boolean, integer, number, array, object (+ formats).
    Postman example bodies only yield JSON types.
    """
    if raw is None:
        return None
    t = str(raw).strip().lower()
    if not t or t in {"null", "any", "n/a", "unknown"}:
        return None
    if t.startswith("array["):
        return "array"
    if t in {"int", "integer", "float", "double", "number", "decimal"}:
        return "number"
    if t == "enum":
        return "string"
    return t
