# spec-doc-sync

Verification tool that checks the OpenAPI specs in this repo against the live
documentation at https://ipgeolocation.io/documentation/<slug>.html.
Pure scripted fetch/parse/diff — no LLM at runtime, safe to run on every change.

## How it works

```
fetch_docs.py  →  .cache/<slug>.html          (curl-level GET, cached; --refresh to re-fetch)
scrape_tables.py → .snapshots/<slug>.json     (field-schema tables per page)
extract_spec_schemas.py → {field: type}       (from local OpenAPI spec or Postman example body)
compare.py     → MISSING / EXTRA / TYPE_MISMATCH report
verify.py      → runs the whole pipeline for every mapping/*.yaml config
```

A table counts as a field-schema table iff its header row starts with
`Field | Type | Description` (extra columns like "Can be empty?" /
"Availability" are fine). Each table is bound to its nearest preceding
`h2/h3/h4`; a `<code>` tag inside the heading gives the object name
("network", "time_zone", ...), otherwise the table is treated as "root"
(standalone-field tables, or the single flat response table on the
simpler APIs). Enum tables, endpoint-availability matrices and the final
HTTP-status table are ignored by construction.

Field comparisons:

| Finding       | Meaning                                        | Severity |
|---------------|------------------------------------------------|----------|
| MISSING       | in docs table, absent from spec schema         | ERROR (exit ≠ 0) |
| EXTRA         | in spec schema, absent from docs table         | WARNING  |
| TYPE_MISMATCH | both present, canonical types differ           | WARNING  |

Type canonicalization before comparison: `float`/`number`/`integer` → `number`,
`array[string]` → `array`, `enum` → `string`. A field whose type cannot be
determined on either side (e.g. `oneOf`-only schemas, null example values) is
never reported as a mismatch.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r tools/spec-doc-sync/requirements.txt
```

## Run

```bash
cd tools/spec-doc-sync
../../.venv/bin/python verify.py                 # all APIs + both root combined files
../../.venv/bin/python verify.py --api asn-api    # one mapping config (file stem)
../../.venv/bin/python verify.py --refresh        # force re-download of doc pages
../../.venv/bin/python verify.py --format json    # machine-readable output
```

Exit code is non-zero only when MISSING fields (real drift) or pipeline errors
are found. EXTRA / TYPE_MISMATCH are warnings and never fail the run.

Individual stages can also be driven by hand:

```bash
../../.venv/bin/python fetch_docs.py ip-location-api --refresh
../../.venv/bin/python scrape_tables.py ip-location-api
../../.venv/bin/python extract_spec_schemas.py ip-location-api/openapi.yaml schema Network
../../.venv/bin/python extract_spec_schemas.py openapi.json postman \
    --folder "IP Geolocation API" --request "Single IP Geolocation Lookup" \
    --response "200 OK – Paid plan, all modules included" --json-path network
../../.venv/bin/python compare.py \
    --snapshot .snapshots/ip-location-api.json --object network \
    --spec-fields <(../../.venv/bin/python extract_spec_schemas.py ip-location-api/openapi.yaml schema Network)
```

## Mapping configs (`mapping/*.yaml`)

One file per API, plus one per root combined file (9 total). Each entry pairs
a doc table with a spec schema:

```yaml
spec_file: ip-location-api/openapi.yaml   # repo-root-relative
source: openapi                            # or: postman
entries:
  - doc_slug: ip-location-api
    doc_object_name: network               # <code> text of the heading, or "root"
    # doc_heading: "Reference to X"        # optional exact heading; wins over object name
    schema_name: Network                   # components.schemas key (openapi source)
    expand: true                           # flatten object $refs one level (asn.peers stays array)
    # ignore_fields: [domain]              # fields conditionally returned (excluded from the diff)
```

Notes on the non-obvious mappings:

- **Flat APIs** (asn, ip-abuse-contact, user-agent): the doc tables use dotted
  rows (`asn.as_number`, `device.name`), so their root entries use
  `expand: true` against the response schema (`ASNLookupResponse`, ...).
- **timezone-api**: doc object `airport_detail` → schema `AirportDetails`;
  the time-conversion table is a second unlabeled table, selected via
  `doc_heading`.
- **root-combined-openapi.yaml**: on the geo side, `IPGeoLocation` is the
  *location object* (not the response — that stays `IpGeolocationResponse`);
  the security endpoint reuses the unprefixed `Security` schema.
- **root-combined-postman.yaml** (`openapi.json` is a Postman v2.1 export, not
  an OpenAPI doc): fields come from the saved example body of
  "IP Geolocation API" > "Single IP Geolocation Lookup" >
  "200 OK – Paid plan, all modules included", via `json_path`.
  `domain` is on `ignore_fields` there: it is only returned when the `ip`
  request parameter holds a domain/hostname, and the example is an IP lookup.

## Caches

- `.cache/<slug>.html` — raw doc pages (gitignored; `--refresh` to update)
- `.snapshots/<slug>.json` — scraped field tables (gitignored, regenerated)
