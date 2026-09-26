# Worklog — live `astroproc audit sparql` run against Wikidata

Date: 2026-09-26
Branch: arena/01a0de0c-astronomical-images-for-wikime
Predecessor: `2026-09-26-reference-implementation-worklog.md`

## What was done

1. Re-tested the network instead of trusting the predecessor's note. It had changed:
   `query.wikidata.org`, `www.wikidata.org`, `mast.stsci.edu` and `heasarc.gsfc.nasa.gov` are
   reachable; SIMBAD and `ps1.stsci.edu` are still blocked; pypi was blocked on the first attempt
   and reachable on the second. `python3 -m venv .venv` fails on this filesystem (lib64 symlink,
   `EPERM`) — the venv went to `/tmp/kilo/astrovenv`, and pytest runs from the repo root because
   `pyproject.toml` already sets `pythonpath`.
2. Ran the audit for real. **The plan's query does not work**: `FILTER(STRSTARTS(?cat, ...))` over
   `wdt:P528` answers 504 after the 60 s WDQS budget (41 402 entries for the NGC prefix alone), and
   the plan's example prefix `"Sh2 "` matches nothing at all. The same scan anchored on
   `?item wdt:P31 wd:Q11282` takes 4–12 s.
3. Rewrote `audit/sparql.py` around two enumeration paths — the Action API search index
   (`haswbstatement:P528=<prefix>* -haswbstatement:P18`, one request, image test included) and a
   class-anchored SPARQL scan for space-separated codes — sharing one batched detail pass that adds
   labels, coordinates and the alias set. Added `--class` to the CLI and made the CLI import astropy
   only in the commands that need it.
4. `experiments/live_audit.py` → per-catalogue gap counts, shortlists and the §6.3 MAST cross-check,
   logged to `experiments/logs/live-audit.log`.
5. plan.md updated: 0.B rewritten with the working queries, new §6.2.1 (live behaviour + the three
   consequences), §16.1 module row, §16.4 validation. findings-pitfalls-skills.md: a Wikidata-at-scale
   section, an imports/CLI section, corrected sandbox notes.

## Validation

- `pytest -q`: 79 passed (was 64; 15 new audit tests, including the HTTP retry contract).
- Live gap counts, stable across three runs: RCW 176 of 220 entries; Sharpless 274 (273 via
  `SH 2-` + 1 via `Sh2`, against 3 through the index); NGC 33 478 of 41 402; IC 6 179; UGC 12 348;
  PGC 13 064; Collinder 3 of 94 (`Coll*` returns 4, one of them a "Collezione" false positive);
  Abell 8 of 13.
- `astroproc audit mast` run live through astroquery: M31 → 15 observations (TESS g,i,r,y,z — a
  real six-filter colour set), M33 → 20 (GALEX FUV/NUV + TESS). The command works; the input does
  not exist yet, because the audit yields designations and no coordinates.
- Both shortlists were checked row by row against the entity JSON and SPARQL by hand
  (Q3928208, Q639464, Q76783721, Q2144471, Q3958747).

## Bugs found and fixed (all found by running against the live service)

- Plan query times out (504) — replaced by an index-backed enumeration.
- `SERVICE wikibase:label` with `"en"` answers the bare Q-id for stubs that only have a `mul` label
  → `"en,mul"`.
- One item, one row per designation: 58 bindings for 26 objects in the first RCW run, so the count
  was inflated 2x. Rows are now grouped by item and the other codes become the alias list.
- `shk 372` passes a naive `startswith("SH")` guard; the index matches per token, so the comparison
  is on tokens — and then over-tightening it to token *equality* emptied the Collinder shortlist
  (`--prefix Coll` reported 4 gaps and showed 0 rows, because the token is "Collinder"). The final
  rule repeats the index semantics (token prefix) and prints every designation, so an over-match is
  visible instead of silently dropped.
- Recursive prefix partitioning was unbounded — a stubbed endpoint that contradicted itself produced
  a `RecursionError`. Depth is now capped at 4.
- `cli.py` imported `pipeline` (and therefore astropy) at module level, so `audit sparql` could not
  run at all without the heavy dependencies.
- Both endpoints fail under load in ways only a live run shows: two of twelve counts died on a
  read timeout, and a shortlist died on an anonymous `429 Too Many Requests`. Every call now retries
  a timeout and honours `Retry-After`; a server-side 504 is deliberately *not* retried, because that
  query was too slow and the WDQS budget would be spent twice for nothing.

## Environment notes

- Live network is partial and flaky, not uniformly blocked; MAST answered (404 on a GET is a
  reachable host) and HEASarc answered 200, but the MAST cross-check still cannot be *fed*: 0 of 327
  Sharpless and 0 of 173 RCW entries in Wikidata carry P625 coordinates, and the resolver that would
  supply them (SIMBAD) is blocked. A name resolver is now a documented prerequisite of §6.3, not an
  optional extra.
- `python3 -m venv` cannot create `.venv` on this mount; use a path outside the repo.

## Next step suggestion

Add a resolver step to the audit — `astroproc audit coords <csv>`, resolving designations against
VizieR/SIMBAD/HEASarc and writing the `name,ra,dec` CSV that `astroproc audit mast` already expects
— then run the §6.3 cross-check for the 274 Sharpless gaps as soon as a resolver host is reachable,
and score the survivors with the §6.5 rubric. That closes the 0.B loop the reference worklog opened:
audit → coordinates → archive coverage → rubric → the first real `astroproc process` run.
