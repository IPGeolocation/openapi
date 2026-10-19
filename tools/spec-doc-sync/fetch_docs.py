#!/usr/bin/env python3
"""Download ipgeolocation.io documentation pages and cache them locally.

The doc pages are server-rendered Next.js HTML; a plain HTTP GET is enough.
Cached pages live in tools/spec-doc-sync/.cache/<slug>.html (gitignored).
"""
from __future__ import annotations

import argparse
import sys

import requests

from common import CACHE_DIR, DOC_BASE_URL, DEFAULT_SLUGS, ensure_dirs

USER_AGENT = "spec-doc-sync/1.0 (+https://ipgeolocation.io)"
TIMEOUT_SECONDS = 60
# Real doc pages are 500KB+; the bogus slug trap (abuse-contact-api.html)
# serves a ~150KB generic placeholder. Anything under this is suspicious.
MIN_PLAUSIBLE_BYTES = 100_000


def fetch_page(slug: str, refresh: bool = False) -> tuple[str, bool]:
    """Return (cache_path, fetched_now). Reuses cache unless refresh=True."""
    ensure_dirs()
    cache_path = CACHE_DIR / f"{slug}.html"
    if cache_path.exists() and not refresh:
        return str(cache_path), False

    url = f"{DOC_BASE_URL}/{slug}.html"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    content = resp.content
    if len(content) < MIN_PLAUSIBLE_BYTES:
        print(
            f"WARNING: {url} is only {len(content):,} bytes — likely a placeholder "
            f"page, not a real doc page. Check the slug.",
            file=sys.stderr,
        )
    cache_path.write_bytes(content)
    return str(cache_path), True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slugs", nargs="*", default=None, help="Doc slugs to fetch (default: all)")
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch even if cached")
    args = parser.parse_args(argv)

    slugs = args.slugs or DEFAULT_SLUGS
    failures = 0
    for slug in slugs:
        try:
            path, fetched = fetch_page(slug, refresh=args.refresh)
            state = "fetched" if fetched else "cached"
            print(f"{slug}: {state} -> {path}")
        except Exception as exc:  # noqa: BLE001 - report and continue per-slug
            failures += 1
            print(f"{slug}: FAILED ({exc})", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
