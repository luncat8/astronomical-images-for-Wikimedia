# Findings, pitfalls, skills

Notes for LLM agents working in this repo. Reusable lessons only; implementation specifics live in plan.md §16 and archive/.

## Sandbox / environment

- Only pypi.org is reliably reachable; Wikimedia, SIMBAD, MAST, PS1 and other astronomy endpoints are blocked at network level. Build network-touching code against the real APIs but keep I/O isolated at module edges (e.g. `audit/sparql.py` separates `missing_p18` from `parse_response`), and validate logic offline with synthetic data.
- **That snapshot was wrong, and it flipped twice in one session (2026-09-26):** query.wikidata.org, www.wikidata.org, mast.stsci.edu and heasarc became reachable while SIMBAD and ps1.stsci.edu stayed blocked, and even pypi timed out on the first attempt and worked on the second. Later the same day vizier.cds.unistra.fr, the simbad.cfa.harvard.edu mirror and cdsarc also answered. Test connectivity per host, do not assume a uniform sandbox, and re-test before declaring a run impossible — a resolver that was blocked is usually blocked at one hostname only.
- **Never pipe a long-running command into `head`.** `astroproc audit coords ... | head -8` died of SIGPIPE after the eighth line and never wrote its output file, which then looked like a stale-result bug. Redirect to a log (`2>&1 | tee log`) or write to a file; a run that both prints a summary and writes an artifact needs `python -u` if you want to watch it.
- `python3 -m venv .venv` **fails on this filesystem**: `Operation not permitted: 'lib' -> '.venv/lib64'`
  (the lib64 symlink), and `--copies` does not help. Create the venv outside the repo
  (`python3 -m venv /tmp/kilo/astrovenv`) and run `pytest` from the repo root — `pyproject.toml`
  already sets `pythonpath = ["tests", "src"]`, so no editable install is needed.
- `.venv/` in the repo root is excluded from session snapshots. Recreate with `python3 -m venv .venv && .venv/bin/pip install -e .[dev]` after resuming; keep `pyproject.toml` authoritative.
- `git push` may fail with "Invalid username or token" — expected, user applies manually (AGENTS.md).

## Wikidata at scale (measured 2026-09-26)

- **`FILTER(STRSTARTS(?cat, ...))` over `wdt:P528` does not scale.** 41 402 NGC entries → HTTP 504
  after the 60 s WDQS budget. `haswbstatement:P528=NGC*` (Action API search index) answers the same
  question in ~1–4 s, and `-haswbstatement:P18` puts the image test in the same indexed request.
  The anchor that makes SPARQL work again is `?item wdt:P31 wd:Q…` — restrict to one class first,
  then filter its string values (4–12 s).
- **A CirrusSearch wildcard binds to the last token only.** `Sh2*` works; `SH 2*` and `NGC 1*`
  return 0 hits, and `Sh2 *` (trailing space) returns 0 too — strip prefixes before building the
  search. Consequence: space-separated catalogue codes are invisible to the index and need the
  class-anchored path.
- **Token matching also over-matches.** The prefix `SH` returns Shk, SHOC, SHADES, SHARDS, SHBL
  and SHJ objects (12 739 hits) alongside the ~310 Sharpless entries. Compare the first *token* of
  the code with the prefix, not leading characters.
- **`SERVICE wikibase:label` with `wikibase:language "en"` returns the bare Q-id** for catalogue
  stubs that only have a `mul` label. Use `"en,mul"`; `?item rdfs:label` with
  `FILTER(LANG(?label) IN ("en","mul"))` also works.
- **One Wikidata item has one row per designation** (NGC 6334 carries 11 P528 values), so a naive
  parse reports the same object 11 times. Group by item and keep the other codes as the alias list —
  which is exactly the cross-identification set §6.2 needs.
- **Catalogue stubs have no coordinates at all**: 0 of 327 Sharpless and 0 of 173 RCW entries carry
  P625. Wikidata is a *designation* source for this workflow, not a coordinate source; a name
  resolver is a prerequisite for the §6.3 MAST cross-check.
- Count with `COUNT(?item)` *inside* an `OPTIONAL` and you count solution rows, not items with the
  optional binding — bind the optional and count that variable, or use `COUNT(DISTINCT ?item)`.
- `list=search` refuses `sroffset` past 10 000, so a prefix with more gaps than that needs
  partitioning — and partitioning only works on a single-token prefix, since you append one
  character to it.
- **Both endpoints are flaky, and the failures are different in kind.** A read timeout or a
  connection error is worth retrying; an anonymous `429` says how long to wait in its `Retry-After`
  header; a WDQS `504` means *your query* was too slow, and retrying spends the budget twice for
  nothing. Only a live run shows this — a twelve-call audit lost two counts and then a shortlist.
- `astroquery.mast` works against the live service from a plain `python3 -m astroproc.cli audit
  mast targets.csv` (M31: 15 observations, TESS g,i,r,y,z). The MAST host answers even when
  SIMBAD and PS1 are blocked, so a partial network still supports the §6.3 check — if the target
  list has coordinates.

## Name resolution (Sesame / CDS)

- **Sesame is the resolver that works when SIMBAD's own host does not.** `simbad.u-strasbg.fr`
  and `simbad.cds.unistra.fr` were blocked while `simbad.cfa.harvard.edu` answered 200, and the
  CDS resolver answers through the VizieR host: `https://vizier.cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV`.
  The `cds.unistra.fr/sesame/` path 404s; the `cgi-bin/nph-sesame` path on the VizieR host
  302-redirects there and must be followed.
- **The batch form is a bare query string, and every other form fails silently.** `?Sh2-104&RCW%205`
  resolves both. `?Name=Sh2-104&Name=RCW+5` and `?Sh2-104=` both return a *well-formed* "nothing
  found" document for the literal names `Name=Sh2-104` and `Sh2-104=` — no error, no exception,
  just an empty result that looks exactly like a catalogue that does not exist. A params dict
  always emits `=`, so build the query string by hand with `urllib.parse.quote(name, safe="")`.
- **A Target carries one Resolver per database and one position each.** Take the first resolver
  with a `jradeg`; a resolver with only `<INFO>from cache</INFO>` has no position and Sesame
  consulted the next database for a reason.
- **Keep the answering catalogue in the output.** `<Resolver name="Sc=Simbad (CDS, via
  client/server)">` vs `N=Ned` vs a survey catalogue is provenance, and a cone search is only as
  good as the position at its centre. The `otype` is the cheap false-positive detector: 250 of 261
  resolved Sharpless gaps came back `HII`, and the other eleven came back as stars, planetary
  nebulae and a bubble — visible without opening a single SIMBAD tab.
- **Nothing found is an answer worth keeping.** The twelve unresolved Sharpless designations
  (`SH 2-52 A`, `SH 2-106 A/B/C`, ...) are all lettered sub-components of a region whose parent
  SIMBAD does know; dropping them from the CSV would have hidden a real, if dull, gap class.

## astroquery / MAST

- **`set(obs["instrument_name"])` raises `TypeError: unhashable type: 'MaskedConstant'`.** MAST
  returns masked values where the instrument or filter is unknown, and a masked value is neither a
  string nor hashable. Go through `column.filled("")` and drop `"--"` and `"CLEAR"`.
- **A cone search finds pointed observations, not survey coverage.** At a 0.1 deg cone, the
  Sharpless positions return something for every single target — TESS sectors, GALEX tiles, SDSS and
  Kepler all answer — so "does data exist?" discriminates nothing, and the cone radius is not even
  the issue. The useful cut is the **pointing separation against the instrument footprint**: an
  ACS/HRC field is 29" and a 3.8'-distant exposure contains none of the object. Compute the
  separation from the observation's own `s_ra`/`s_dec` and compare it with the field of view, or the
  shortlist will be six targets that do not exist.
- **The product-listing service was down for the whole session (2026-09-26, later).**
  `Observations.get_product_list` and `Observations.query_criteria(obsid=...)` both fail with
  `RemoteServiceError: Error converting data type varchar to bigint` — a MAST-side database fault,
  not a client error — while the *cone search* keeps answering. `download_products` goes through the
  broken path, so it fails too.
  The **Download service itself is healthy** and the per-visit products follow a fixed naming
  convention, so build the URI instead of looking it up:
  `https://mast.stsci.edu/api/v0.1/Download/file?uri=mast:HST/product/<obsid>/<obsid>_drz.fits`
  with `Range: bytes=0-0` as a 41-byte existence probe, then the same URI for the body. `_drc` (the
  preferred level, CTE-corrected) does not exist for WFC3/IR, so probe the levels in order.
- **A FITS header is the better provenance source anyway.** With the metadata service failing,
  `BUNIT`/`INSTRUME`/`FILTER`/`EXPTIME`/`PROPOSID`/`TARGNAME` in the file are authoritative and cost
  nothing. They are also where the cross-identification lives: the WFC3 file fetched as "SH 2-252 F"
  declares `TARGNAME = NGC 2174`, and NGC 2174 is already illustrated on Commons *and* on Wikipedia.
  A candidate's real name is frequently absent from its Wikidata item (P528 held only `SH 2-252 F`).

## Non-finite pixels in real archive products

The same class of bug, found four times in one run, and the synthetic test scene cannot find it
because it has no blank coverage. A dithered or mosaicked product writes NaN (or inf) where there was
no exposure, and **almost every percentile silently returns NaN**:

- `np.percentile` on an array with a few NaN pixels returns NaN, and `NaN > threshold` is `False`.
  The §7.1 verdict metric became NaN, and a *stretched* product is exactly the case where the
  comparison must not default to "linear".
- `np.median` over star fluxes containing one NaN made the whole R/B report `nan, nan` on an
  otherwise ordinary frame. Star apertures that reach into blank coverage must be **dropped**, not
  zero-filled: a filled aperture invents a dark measurement.
- `auto_params` returned `high_point=nan`, which propagates through the asinh and turns the entire
  composite into blank coverage.
- `np.clip` does not touch NaN, so the 8-bit and 16-bit casts emitted
  `RuntimeWarning: invalid value encountered in cast` and wrote garbage pixels.

Rule: every statistic is computed on the finite subset, the invalid fraction is reported next to the
result, and blank coverage becomes black on export.

## A histogram needs exposed sky

The §7.1 test ("narrow sky peak + long tail" vs "flat and wide") assumes the frame contains
background sky. **A nebula that fills the frame has no sky peak**: its median sits inside the
object's own light, so median/span reads high and linear data is refused with the wrong reason —
measured on a linear WFC3/IR drizzle at 0.25 against a 0.02 threshold, while the plan itself tells
you to start at drz/drc products. A product that declares a physical `BUNIT` **and** standard
pipeline provenance (`NCOMBINE`, `DRIZCORR`, `CAL_VER`, `PFLTFILE`, `OPUS_VER`) is linear by
construction; the header then outranks the histogram and the disagreement is written into the report.
`BUNIT = DN` counts as no evidence: it is also the unit of a stretched 8-bit preview.

## Two defaults that were never choices

- `build_stretch_params` filled any key the config omitted with `shadow_clip=0.0`,
  `high_point=1.0`. Those are plausible defaults **in normalised pixel units and nowhere else**: on a
  real product in electrons/s they compress the object into the top octave, and nothing in the log
  said the numbers had not been chosen. Auto is now per key.
- `out_dir` was resolved against the shell's working directory while every *input* path was resolved
  against the config file, so a run started from the repository root wrote its entire output tree
  (`data-linear.fits`, 13 MB, `presentation.png`, log) to `/media/sf_1/data/` — outside the project.

## Editing files in this agent environment

- Batched parallel edits to *several* files can silently keep only one of the changes — after any edit batch, re-verify each file on disk (grep the edited line) before building on it. Same for two edits to the same file in one batch. Single edits are reliable; `bash` heredoc rewrites are reliable.

## NumPy / astropy

- `np.median` on an all-NaN slice returns NaN with only a RuntimeWarning, no exception. NaN then flows silently into percentiles and every downstream number (`high_point=nan` taught us). After any nan-producing reduction, either interpolate (see `_median_profile` in `post.py`) or assert finiteness.
- `(3, H, W) @ (3,)` raises — matmul treats the leading dim as M. Use `np.einsum("i...,i->...")` for weighted luma over channel-first arrays.
- Fractional powers of negative (sky-subtracted) pixels are NaN: `np.power(x, 0.95)` on noise around 0 poisons the array. Floor at 0 before any fractional gamma.
- `sigma_clipped_stats` copies the array several times — on a 4k² float32 composite that is ~700 MB and 10x the runtime of the stretch itself. A strided subsample (~4M pixels) gives a statistically identical median at fixed cost.
- The asinh stretch saturates star cores to (1,1,1) regardless of colour: judge star colour in the *wings*, never at the peak pixel. Tests must sample wings.
- A shared-stretch invariance test must feed the *same* values to every channel (e.g. an identical patch). Random per-channel data cannot distinguish a correct shared stretch from a broken per-channel one.
- `astropy.wcs`: writing `crota` is deprecated — use the PC matrix. Flipping cdelt on *both* axes is a 180° rotation, not a mirror; a mirror flips exactly one axis.
- `astroquery.mast`: `Observations.query_criteria` silently ignores unknown kwargs such as `filters`; filter products afterwards instead.

## Pillow

- `Image.fromarray(..., mode="RGB")` is deprecated (removal in Pillow 13); uint8 `(H, W, 3)` infers RGB on its own. `fromarray` needs channel-last — keep one `_hwc` transpose adapter at the export boundary, channel-first (3, H, W) everywhere else.

## Strings / formats

- SPARQL queries built with `str.format` need every literal brace escaped (`{{ }}`) — SPARQL is brace-dense, so consider `string.Template` or replacement next time. Building a query from *concatenated* fragments (a shared `CLASS_TAIL`) and formatting only the values keeps the escaping to one place.

## Python structure

- A CLI that imports the heavy pipeline at module level cannot run its light subcommands on a
  machine without the heavy dependencies: `astroproc audit sparql` needs only `requests`, but the
  astropy-importing `pipeline` was pulled in by the same top-level import. Import inside the
  command that needs it.
- Recursion over a remote API needs an explicit depth bound even when the data "cannot" loop — one
  stubbed `totalhits` that contradicted its own parts turned prefix partitioning into a
  `RecursionError`, and a test that fakes an endpoint should fake it *impossibly* to catch that.
- A guard is only a guard if it is anchored to the data model, and it must not be *stricter* than
  the source it filters: requiring the first token to equal the prefix looked tidy and silently
  emptied a real shortlist (`--prefix Coll` → 4 rows became 0, because the tokens are "Collinder").
  Reproduce the endpoint's matching semantics and let over-matching stay visible in the output.

## Testing pipeline code

- A synthetic scene with planted ground truth (star colour classes, sky levels per channel, throughput factors, one saturated star, TAN WCS) pays for itself many times over: it caught NaN propagation, a no-op metric, a matmul misuse, mirror/rotation bugs, and it doubles as the demo generator.
- Assert log *completeness* (every template line either filled or visibly `<TODO>`), not just absence of exceptions — the log is a deliverable (plan §7.9, §13.2).

## Coverage audits that join commands (2026-09-27)

- **`wbgetentities` caps `ids` at 50 per request.** One request for a 274-row shortlist answers with
  the first 50 items and **no error**, which reads exactly like "most gaps are covered". Batch every
  bulk id list and pin the batch size in a test; the same class of silent truncation applies to any
  API with a `max` on a comma/pipe-separated parameter.
- **Compute a derived count where the row is built, not where the CSV is written.** `n_category_files`
  existed only inside `write_candidates`, so the command that printed its own rows raised `KeyError`
  on the first one. The CSV writer should only join lists; every field the terminal output reads has
  to be on the row.
- **A string that joins two commands belongs in one place.** The verdicts that mean "the archive
  answered" lived as `ANSWER_VERDICTS` in `commons` and as a literal `"imaged"` in `score`, so the
  second verdict (`colour_set`) silently stopped counting as coverage. One tuple, imported.
- **An empty field is not a default worth inventing.** A blank `rights` column must leave the licence
  gate unscored rather than pass it; a set with no release date must stay a candidate rather than be
  filtered as old. Say "unknown" and let the operator see it.
- **Gate a candidate's evidence on the test that produced it.** A pointing that misses the object by
  3.84' still has a filter, a frame size and an observation id, and filling the dossier with them
  makes an empty field look like data. Show the miss (with its separation) where the data source
  goes; leave the channels blank.
- **Keep the non-answers in the output as their own verdicts.** `footprint_missed`,
  `footprint_unreadable`, `no_pointed_data`, `no_coordinates`, `released_before_window` and
  `fewer_filters_than_requested` send the operator to six different places, and collapsing them into
  an empty table is how "not checked" gets read as "nothing there". Same rule as the NaN work
  earlier: report the invalid/undecided fraction beside the result.
- **Reuse the producer's private helpers by promoting them, not by copying.** Two modules needed the
  same `;`/`,`-separated designation split; the second copy was avoided by making `coords.split_codes`
  public, and `mast._read_targets` became `mast.read_targets` when `sets.py` needed it. A private name
  imported across modules is a rename that was missed.
