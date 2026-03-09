# GlobaLeaks Directory Seed

This repository can surface GlobaLeaks instances in the Hush Line directory through a checked-in
JSON artifact generated from an operator-supplied export.

## Data source

- Local artifact: `hushline/data/globaleaks_instances.json`
- Intended upstream input: automated export of GlobaLeaks instances, for example a Shodan-derived
  discovery set

## Refresh the artifact

Use the importer script against a local export file:

```bash
make refresh-globaleaks-listings \
  REFRESH_GLOBALEAKS_ARGS="--input /path/to/globaleaks-export.json --source-url https://www.shodan.io/"
```

Supported input formats:

- JSON array of objects
- JSON object with a `matches` array
- JSONL / NDJSON
- CSV with a header row

The normalizer accepts either already-normalized rows or Shodan-style host exports. It derives a
stable `globaleaks~...` slug from the host, a canonical `submission_url`, a fallback `website`,
country/language lists when present, deterministic ordering, and duplicate rejection.

Use `--check` to verify that `hushline/data/globaleaks_instances.json` is already up to date.

## Required fields per normalized row

- `id`
- `slug`
- `name`
- `website`
- `description`
- `submission_url`
- `source_label`
- `source_url`

Optional fields:

- `host`
- `countries`
- `languages`

## Current model

- The checked-in artifact is the source of truth and is loaded at runtime, similar to other
  directory-backed listing types.
- The current checked-in seed includes a starter set of public GlobaLeaks destinations gathered
  from GlobaLeaks' own use-case pages, linked live instance domains, and publicly accessible
  Shodan host pages.
- The refresh script normalizes operator-supplied export data into the checked-in schema before
  merge.
- Listing pages are read-only and must not imply that the destination is operated by Hush Line.

## Follow-up

- Decide whether the source export should live in a private bucket or release asset, or remain a
  local operator input.
- Decide whether this should eventually move into a scheduled or manually-dispatched workflow.
- Determine whether we need more metadata, for example onion-only versus clearnet-capable.
