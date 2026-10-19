#!/usr/bin/env python3
"""Top-level verifier: docs at ipgeolocation.io vs local OpenAPI specs.

Pipeline per mapping entry: fetch (cached) -> scrape -> extract -> compare.
Exit code is non-zero only when MISSING fields are found (or a pipeline step
fails outright), so it is safe to run in CI on every change.

Usage:
  python verify.py                     # everything
  python verify.py --api asn-api       # one mapping config (file stem)
  python verify.py --refresh           # force re-fetch of doc pages
  python verify.py --format json       # machine-readable report
"""
from __future__ import annotations

import argparse
import json
import sys

from common import MAPPING_DIR, SNAPSHOT_DIR, ensure_dirs, load_structured, resolve_repo_path
from compare import compare_fields, doc_rows_to_types, field_line, find_doc_table, format_report
from extract_spec_schemas import extract_openapi_schema, extract_postman_body
from fetch_docs import fetch_page
from scrape_tables import write_snapshot


def load_mapping_configs(only: list[str] | None) -> list[tuple[str, dict]]:
    configs = []
    for path in sorted(MAPPING_DIR.glob("*.yaml")):
        if only and path.stem not in only:
            continue
        configs.append((path.stem, load_structured(path)))
    return configs


def get_snapshot(slug: str, refresh: bool) -> dict:
    snap_path = SNAPSHOT_DIR / f"{slug}.json"
    if refresh or not snap_path.exists():
        fetch_page(slug, refresh=refresh)
        write_snapshot(slug)
    return json.loads(snap_path.read_text(encoding="utf-8"))


def run_entry(mapping_name: str, entry: dict, spec: dict, refresh: bool) -> dict:
    slug = entry["doc_slug"]
    object_name = entry.get("doc_object_name", "root")
    heading = entry.get("doc_heading")
    label = f"{mapping_name} :: {slug} :: {heading or object_name}"

    snapshot = get_snapshot(slug, refresh)
    try:
        table = find_doc_table(snapshot["tables"], object_name=object_name, heading=heading)
    except LookupError as exc:
        return {"label": label, "status": "error", "error": str(exc)}

    source = entry.get("_source", "openapi")
    try:
        if source == "postman":
            pm = entry["_postman"]
            spec_fields = extract_postman_body(
                spec,
                folder=pm["folder"],
                request_name=pm["request"],
                response_name=pm["response"],
                json_path=entry.get("json_path", ""),
            )
        else:
            schema_name = entry["schema_name"]
            expand = bool(entry.get("expand", True))
            spec_fields = extract_openapi_schema(spec, schema_name, expand=expand)
    except Exception as exc:  # noqa: BLE001 - surfaced per-entry
        return {"label": label, "status": "error", "error": str(exc)}

    report = compare_fields(
        doc_rows_to_types(table["rows"]),
        spec_fields,
        ignore=set(entry.get("ignore_fields") or []),
    )
    return {
        "label": label,
        "status": "ok",
        "doc_slug": slug,
        "doc_object": table.get("object_name") or "root",
        "doc_heading": table.get("heading_text"),
        "spec_side": entry.get("schema_name")
        or f'postman:{entry.get("json_path") or "<body>"}',
        "doc_fields": len(table["rows"]),
        "spec_fields": len(spec_fields),
        **report,
    }


def print_text(results: list[dict], mapping_names: list[str]) -> None:
    width = max((len(r["label"]) for r in results), default=20)
    header = (
        f"{'comparison'.ljust(width)}  {'doc':>4} {'spec':>5} "
        f"{'MISS':>4} {'EXTRA':>5} {'TYPE':>4}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        if r["status"] != "ok":
            print(f"{r['label'].ljust(width)}  ERROR: {r['error']}")
            continue
        print(
            f"{r['label'].ljust(width)}  {r['doc_fields']:>4} {r['spec_fields']:>5} "
            f"{len(r['missing']):>4} {len(r['extra']):>5} {len(r['type_mismatch']):>4}"
        )
    print()
    for r in results:
        if r["status"] == "ok" and (
            r["missing"] or r["extra"] or r["type_mismatch"]
        ):
            print(format_report(r["label"], r))
    print()
    errors = [r for r in results if r["status"] != "ok"]
    missing_total = sum(len(r.get("missing", [])) for r in results if r["status"] == "ok")
    if errors or missing_total:
        bits = []
        if missing_total:
            bits.append(f"{missing_total} MISSING field(s)")
        if errors:
            bits.append(f"{len(errors)} pipeline error(s)")
        print(f"FAIL: {'; '.join(bits)} across {len(mapping_names)} mapping config(s)")
    else:
        warnings = sum(
            len(r["extra"]) + len(r["type_mismatch"]) for r in results if r["status"] == "ok"
        )
        suffix = f" ({warnings} warning(s): EXTRA / TYPE_MISMATCH)" if warnings else ""
        print(f"PASS: no MISSING fields across {len(mapping_names)} mapping config(s){suffix}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api",
        action="append",
        default=None,
        help="Only run this mapping config (file stem, e.g. asn-api). Repeatable.",
    )
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch of doc pages")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    ensure_dirs()
    all_stems = sorted(p.stem for p in MAPPING_DIR.glob("*.yaml"))
    if args.api:
        unknown = [a for a in args.api if a not in all_stems]
        if unknown:
            print(
                f"Unknown --api value(s): {', '.join(unknown)}. "
                f"Available: {', '.join(all_stems)}",
                file=sys.stderr,
            )
            return 2
    configs = load_mapping_configs(args.api)
    if not configs:
        print(f"No mapping configs found in {MAPPING_DIR}", file=sys.stderr)
        return 2

    results: list[dict] = []
    for name, config in configs:
        spec_path = resolve_repo_path(config["spec_file"])
        source = config.get("source", "openapi")
        spec = load_structured(spec_path)
        for entry in config.get("entries") or []:
            entry = dict(entry)
            entry["_source"] = source
            if source == "postman":
                entry["_postman"] = config["postman"]
            results.append(run_entry(name, entry, spec, refresh=args.refresh))

    names = [name for name, _ in configs]
    if args.format == "json":
        payload = {
            "mapping_configs": names,
            "results": results,
            "pass": all(
                r["status"] == "ok" and not r["missing"] for r in results
            ),
        }
        json.dump(payload, sys.stdout, indent=2)
        print()
    else:
        print_text(results, names)

    return 0 if all(r["status"] == "ok" and not r["missing"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
