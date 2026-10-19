#!/usr/bin/env python3
"""Scrape field-schema tables out of cached documentation HTML.

A table is treated as a field-schema table iff its first row starts with the
columns Field | Type | Description (case-sensitive), regardless of trailing
columns (docs add "Can be empty?" and sometimes "Availability").

Each such table is associated with its nearest preceding h2/h3/h4 heading.
If the heading contains a <code> tag, the code text is the object name
(e.g. "network"); otherwise the table is unlabeled ("root" from the caller's
perspective — e.g. standalone-field tables or a single flat response table).

Output snapshot: tools/spec-doc-sync/.snapshots/<slug>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from common import CACHE_DIR, DEFAULT_SLUGS, SNAPSHOT_DIR, ensure_dirs

FIELD_HEADER_PREFIX = ["Field", "Type", "Description"]
HEADING_TAGS = ["h2", "h3", "h4"]


def _cell_text(cell) -> str:
    return cell.get_text(" ", strip=True)


def parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    tables = []
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if first_row is None:
            continue
        header = [_cell_text(c) for c in first_row.find_all(["th", "td"])]
        if header[:3] != FIELD_HEADER_PREFIX:
            continue  # availability matrix, enum table, HTTP-status table, ...

        heading = table.find_previous(HEADING_TAGS)
        heading_text = heading.get_text(" ", strip=True) if heading else None
        code = heading.find("code") if heading else None
        object_name = code.get_text(strip=True) if code else None

        rows = []
        for tr in table.find_all("tr")[1:]:
            cells = [_cell_text(c) for c in tr.find_all(["th", "td"])]
            if not cells or not cells[0]:
                continue
            rows.append(
                {
                    "field": cells[0],
                    "type": cells[1] if len(cells) > 1 else None,
                    "description": cells[2] if len(cells) > 2 else None,
                    "can_be_empty": cells[3] if len(cells) > 3 else None,
                    "availability": cells[4] if len(cells) > 4 else None,
                }
            )

        tables.append(
            {
                "heading_text": heading_text,
                "object_name": object_name,
                "columns": header,
                "rows": rows,
            }
        )
    return tables


def scrape_slug(slug: str) -> dict:
    cache_path = CACHE_DIR / f"{slug}.html"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"No cached page for '{slug}' at {cache_path}. Run fetch_docs.py first."
        )
    html = cache_path.read_text(encoding="utf-8", errors="replace")
    return {
        "slug": slug,
        "source_url": f"https://ipgeolocation.io/documentation/{slug}.html",
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": parse_page(html),
    }


def write_snapshot(slug: str) -> str:
    ensure_dirs()
    snapshot = scrape_slug(slug)
    out = SNAPSHOT_DIR / f"{slug}.json"
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slugs", nargs="*", default=None, help="Slugs to scrape (default: all)")
    parser.add_argument("--all", action="store_true", help="Scrape every known slug")
    args = parser.parse_args(argv)

    slugs = args.slugs or DEFAULT_SLUGS
    failures = 0
    for slug in slugs:
        try:
            out = write_snapshot(slug)
            snapshot = json.loads(open(out, encoding="utf-8").read())
            n_rows = sum(len(t["rows"]) for t in snapshot["tables"])
            print(f"{slug}: {len(snapshot['tables'])} field table(s), {n_rows} row(s) -> {out}")
        except Exception as exc:  # noqa: BLE001 - report and continue per-slug
            failures += 1
            print(f"{slug}: FAILED ({exc})", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
