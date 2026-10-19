#!/usr/bin/env python3
"""Diff a documentation field table against a spec schema's {field: type} map.

Severity model:
  MISSING      - field in docs but not in spec  -> ERROR (real drift; exit-worthy)
  EXTRA        - field in spec but not in docs  -> WARNING (may be undocumented-but-legit)
  TYPE_MISMATCH- both sides, different type     -> WARNING (after type canonicalization:
                 float/number/integer, array[T]/array, enum/string all compare equal)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import canon_type


def find_doc_table(tables: list[dict], object_name: str | None = None, heading: str | None = None) -> dict:
    """Pick the field table for a mapping entry.

    heading: exact match on the preceding heading text (wins if set) — needed
             when a page has multiple unlabeled tables.
    object_name: match on the <code> text of the heading; "root"/None selects
                 the first unlabeled table in document order.
    """
    if heading is not None:
        for table in tables:
            if table.get("heading_text") == heading:
                return table
        raise LookupError(f"No field table with heading {heading!r}")

    if object_name in (None, "root"):
        for table in tables:
            if table.get("object_name") is None:
                return table
        raise LookupError("No unlabeled (root) field table found")

    for table in tables:
        if table.get("object_name") == object_name:
            return table
    raise LookupError(f"No field table for object '{object_name}'")


def doc_rows_to_types(rows: list[dict]) -> dict:
    return {row["field"]: canon_type(row.get("type")) for row in rows}


def compare_fields(doc_types: dict, spec_types: dict, ignore: set | None = None) -> dict:
    ignore = ignore or set()
    missing = sorted(f for f in doc_types if f not in spec_types and f not in ignore)
    extra = sorted(f for f in spec_types if f not in doc_types and f not in ignore)
    mismatches = []
    for field in sorted(set(doc_types) & set(spec_types)):
        if field in ignore:
            continue
        doc_t, spec_t = canon_type(doc_types[field]), canon_type(spec_types[field])
        if doc_t is not None and spec_t is not None and doc_t != spec_t:
            mismatches.append({"field": field, "doc_type": doc_t, "spec_type": spec_t})
    return {"missing": missing, "extra": extra, "type_mismatch": mismatches}


def format_report(label: str, report: dict) -> str:
    lines = [f"== {label}"]
    n = len(report["missing"]) + len(report["extra"]) + len(report["type_mismatch"])
    if n == 0:
        lines.append("   OK (no drift)")
        return "\n".join(lines)
    for field in report["missing"]:
        lines.append(f"   ERROR   MISSING       {field} (in docs, not in spec)")
    for field in report["extra"]:
        lines.append(f"   warning EXTRA         {field} (in spec, not in docs)")
    for m in report["type_mismatch"]:
        lines.append(
            f"   warning TYPE_MISMATCH {field_line(m)}"
        )
    return "\n".join(lines)


def field_line(m: dict) -> str:
    return f"{m['field']} (docs={m['doc_type']}, spec={m['spec_type']})"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="Path to a scraped <slug>.json snapshot")
    parser.add_argument("--object", default="root", help='Doc object name (code text) or "root"')
    parser.add_argument("--heading", default=None, help="Exact preceding heading text (overrides --object)")
    parser.add_argument("--spec-fields", required=True, help="Path to a {field: type} JSON file")
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Field to exclude from the diff (repeatable), e.g. conditionally-returned fields",
    )
    args = parser.parse_args(argv)

    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    spec_types = json.loads(Path(args.spec_fields).read_text(encoding="utf-8"))
    table = find_doc_table(snapshot["tables"], object_name=args.object, heading=args.heading)
    report = compare_fields(doc_rows_to_types(table["rows"]), spec_types, ignore=set(args.ignore))
    label = f"{snapshot['slug']} :: {table.get('object_name') or 'root'} ({table['heading_text']})"
    print(format_report(label, report))
    return 1 if report["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
