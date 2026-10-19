#!/usr/bin/env python3
"""Extract {field: type} for a single schema from a local OpenAPI spec.

OpenAPI mode: reads components.schemas[schema_name] and maps each *direct*
property to its type. Object-typed properties that are $refs are resolved one
level: with expand=True they become dotted fields (asn.as_number, dst_start.utc_time)
matching how the docs flatten nested objects; array-of-$ref properties are left
as plain "array" (docs don't expand array items). Nested object properties'
*own* sub-schemas are NOT recursed further — those correspond to separate doc
tables, which are compared via their own mapping entries.

Postman mode: the root openapi.json is a Postman v2.1 collection, not an
OpenAPI document. Fields are taken from a saved example response body under
folder > request > response, optionally navigated to a nested object via
json_path (e.g. "network"). Types are inferred from JSON values.
"""
from __future__ import annotations

import argparse
import json
import sys

from common import load_structured, resolve_repo_path

FORMAT_TYPE_MAP = {
    "int32": "integer",
    "int64": "integer",
    "float": "number",
    "double": "number",
}


def _resolve_ref(spec: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"Unsupported $ref (expected local): {ref}")
    node = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def _declared_type(node: dict) -> str | None:
    """Type of a schema node without expanding its properties."""
    if not isinstance(node, dict):
        return None
    t = node.get("type")
    if isinstance(t, list):  # OpenAPI 3.1 nullable unions
        t = next((x for x in t if x != "null"), None)
    if t:
        return t
    if "properties" in node or "allOf" in node or "oneOf" in node or "anyOf" in node:
        return "object"
    if "items" in node:
        return "array"
    fmt = node.get("format")
    if isinstance(fmt, str):
        return FORMAT_TYPE_MAP.get(fmt)
    return None


def _simple_type(spec: dict, node: dict) -> str | None:
    """Type of a property schema; $refs resolved only for type lookup."""
    if not isinstance(node, dict):
        return None
    if "$ref" in node:
        return _declared_type(_resolve_ref(spec, node["$ref"]))
    if "allOf" in node and len(node["allOf"]) == 1 and "$ref" in node["allOf"][0]:
        return _declared_type(_resolve_ref(spec, node["allOf"][0]["$ref"]))
    t = _declared_type(node)
    if t:
        return t
    if "allOf" in node:  # merge-less heuristic: object-ish composition
        return "object"
    return None


def _is_object_like(node: dict) -> bool:
    return bool(node.get("properties")) or bool(
        any("properties" in m for m in node.get("allOf", []) if isinstance(m, dict))
    )


def _object_ref_target(spec: dict, prop: dict):
    """Return the referenced object schema if prop wraps a $ref to one.

    Handles the shapes used in these specs:
      {$ref: ...}
      {allOf: [{$ref: ...}]}
      {oneOf: [{$ref: ...}, {type: object, maxProperties: 0}]}   # nullable object
    Returns None if prop is not a ref (inline schema) or the target is not
    object-like (e.g. arrays stay plain "array" — docs don't expand items).
    """
    ref = prop.get("$ref")
    if ref is None and len(prop.get("allOf") or []) == 1 and isinstance(prop["allOf"][0], dict):
        ref = prop["allOf"][0].get("$ref")
    if ref is None:
        refs = [
            m.get("$ref")
            for m in (prop.get("oneOf") or [])
            if isinstance(m, dict) and "$ref" in m
        ]
        if len(refs) == 1:
            ref = refs[0]
    if ref is None:
        return None
    target = _resolve_ref(spec, ref)
    return target if _is_object_like(target) else None


def _own_properties(node: dict) -> dict:
    props = dict(node.get("properties") or {})
    for member in node.get("allOf", []):
        if isinstance(member, dict):
            props.update(member.get("properties") or {})
    return props


def extract_openapi_schema(spec: dict, schema_name: str, expand: bool = True) -> dict:
    schemas = (spec.get("components") or {}).get("schemas") or {}
    if schema_name not in schemas:
        raise KeyError(
            f"Schema '{schema_name}' not found in components.schemas "
            f"(available: {', '.join(sorted(schemas))})"
        )
    schema = schemas[schema_name]
    fields: dict = {}
    for name, prop in _own_properties(schema).items():
        if not isinstance(prop, dict):
            continue
        target = _object_ref_target(spec, prop)
        if target is not None:
            if expand:
                for sub_name, sub_prop in _own_properties(target).items():
                    fields[f"{name}.{sub_name}"] = _simple_type(spec, sub_prop)
            else:
                fields[name] = _declared_type(target)
        elif "$ref" in prop:
            fields[name] = _declared_type(_resolve_ref(spec, prop["$ref"]))
        else:
            fields[name] = _simple_type(spec, prop)
    return fields


def _json_type(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return None


def _find_named(items: list, name: str, kind: str) -> dict:
    for item in items or []:
        if item.get("name") == name:
            return item
    raise KeyError(f"{kind} '{name}' not found")


def extract_postman_body(
    collection: dict,
    folder: str,
    request_name: str,
    response_name: str,
    json_path: str = "",
) -> dict:
    folder_item = _find_named(collection.get("item") or [], folder, "folder")
    request_item = _find_named(folder_item.get("item") or [], request_name, "request")
    response = _find_named(request_item.get("response") or [], response_name, "response")
    body = response.get("body")
    data = json.loads(body) if isinstance(body, str) else body
    if not isinstance(data, dict):
        raise ValueError(f"Response body for '{response_name}' is not a JSON object")
    node = data
    if json_path:
        for part in json_path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise KeyError(f"json_path '{json_path}' not found in response body")
            node = node[part]
        if not isinstance(node, dict):
            raise ValueError(f"json_path '{json_path}' does not point at an object")
    return {k: _json_type(v) for k, v in node.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec_file", help="Path to an OpenAPI json/yaml file or Postman collection")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_oa = sub.add_parser("schema", help="OpenAPI: fields of components.schemas[NAME]")
    p_oa.add_argument("schema_name")
    p_oa.add_argument("--no-expand", action="store_true", help="Do not flatten object $refs one level")

    p_pm = sub.add_parser("postman", help="Postman: fields of an example response body")
    p_pm.add_argument("--folder", required=True)
    p_pm.add_argument("--request", required=True)
    p_pm.add_argument("--response", required=True)
    p_pm.add_argument("--json-path", default="", help='Dotted path to a nested object, e.g. "network"')

    args = parser.parse_args(argv)
    doc = load_structured(resolve_repo_path(args.spec_file))
    if args.mode == "schema":
        fields = extract_openapi_schema(doc, args.schema_name, expand=not args.no_expand)
    else:
        fields = extract_postman_body(doc, args.folder, args.request, args.response, args.json_path)
    json.dump(fields, sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
