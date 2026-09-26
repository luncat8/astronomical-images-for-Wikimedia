# Worklog — name resolver, live §6.3 cross-check, and the first rubric shortlist

Date: 2026-09-26
Branch: arena/01a0de0c-astronomical-images-for-wikime
Predecessor: `2026-09-26-live-sparql-audit-worklog.md`

## What was done

1. **Re-tested the network** (it had moved again): `vizier.cds.unistra.fr`, `vizier.cfa.harvard.edu`,
   `simbad.cfa.harvard.edu`, `cdsarc.cds.unistra.fr`, HEASARC, MAST and Wikidata all answer.
   SIMBAD's own hosts (`simbad.cds.unistra.fr`, `simbad.u-strasbg.fr`) and PS1 remain blocked — so
   the predecessor's "a resolver is needed" note was solvable, and nothing had to be fetched by hand.
2. **`audit/coords.py`: designation → ICRS coordinates** through Sesame, the CDS resolver
   (one request per 25 names), with the answering catalogue kept in the `source` column and the
   returned `otype` as a free false-positive detector. A name that fails is retried with the
   cross-identifications the audit already collected, bounded to three.
3. **`audit/http.py`**: the retry contract (read timeout → retry, 429 → wait `Retry-After`,
   504 → never) extracted from `sparql.py` so the resolver and the audit share it.
4. **The chain became file-based**: `audit sparql --out` writes a gap CSV (designation, aliases,
   item, label, ra, dec), `audit coords --csv|--prefix` writes the `name,ra,dec` CSV that
   `audit mast` reads, `audit mast` gained `--radius` and counts the targets it had to skip.
5. **Ran the §6.3 cross-check for real** over all 273 Sharpless gaps (`experiments/logs/live-audit.log`):
   261 resolved, 261 cone searches at 0.1°, **6 targets with pointed HST/JWST data**.
6. **`experiments/commons_gap.py`**: the check P18 cannot do — cross-identifications, Commons
   category, enwiki lead image, full-text hits as noise (`experiments/logs/commons-gap.log`).
7. plan.md: new §6.3.1 with the measured numbers and the three consequences; §6.2.1 gains the
   fourth (the client guard must repeat the server's rule, per path); §1 0.B, §0.9, §16.1, §16.4.
   findings-pitfalls-skills.md: resolver, MAST and environment sections.

## Validation

- `pytest -q`: 96 passed (was 79; 17 new — Sesame parsing, the silent-wrong-URL contract,
  batch form, ordering, alias retry and its bound, CSV round trip, masked MAST columns, skip
  counting, the per-path prefix guard, and the retry contract against the shared module).
- Gap counts reproduce the previous run exactly (NGC 33 478, IC 6 177, RCW 176, Abell 8, UGC
  12 348, PGC 13 062, `SH 2-` 273), so the two runs are comparable.
- Resolution 261/273 = 95.6 %; the 12 failures are all lettered sub-components of regions SIMBAD
  knows only whole (`SH 2-106 A/B/C`, `SH 2-52 A`, …). No Sharpless gap needed the alias retry —
  the stubs carry one P528 code each — which is why the retry matters for RCW/NGC, not here.
- MAST at 0.1°: **261 of 261** have imaging (TESS `Photometer`/`GPC1` 258, GALEX 120, SDSS 41,
  Kepler 33, HST 60+, JWST 18). 6 have pointed HST/JWST: `SH 2-1`, `SH 2-7`, `SH 2-20`,
  `SH 2-252 F`, `SH 2-285`, `SH 2-289`.
- Commons/enwiki on those 6: no Commons category for any; enwiki articles for `Sh 2-1` and
  `Sh 2-7` have **no lead image**; `Sh 2-20` is illustrated as `RCW 141` (the P18 proxy was wrong).

## Bugs found and fixed (all found by running against the live service)

- **The client-side prefix guard was wrong for the anchored path.** `_matches` used the search
  index's token rule for both paths, so a shortlist for `SH 2-` listed two items under names from
  *outside* the scanned class: `SH 1-15` and `SH 1-5`, which are cross-identifications of `SH 2-20`
  and `SH 2-4`. Two rows of 273, both wrong names to resolve. The guard now repeats the rule the
  server used, per path (`anchored` → `STRSTARTS`).
- **The Sesame batch form is a bare query string, and every other form fails silently.**
  `?Name=Sh2-104&Name=RCW+5` resolves the literal name `Name=Sh2-104` and answers a well-formed
  "nothing found" document — the first implementation reported 0 of 3 resolved and looked like a
  catalogue problem. `?Sh2-104&RCW%205` is the form; a params dict always emits `=`, so the query
  string is hand-built with `quote(name, safe="")`.
- **`set(obs["instrument_name"])` raises `TypeError: unhashable type: 'MaskedConstant'`** on the
  first live target: MAST masks the instrument where it is unknown. Columns now go through
  `filled("")`, and `"--"`/`"CLEAR"` are dropped as the placeholders they are.
- **A piped run that prints a summary *and* writes a file loses the file.** `audit coords | head -8`
  died of SIGPIPE before `write_targets`, and the stale CSV then looked like a stale-result bug.
  Log to a file with `tee`, or `python -u`, and never truncate a long run into `head`.
- **`commons_gap.py` first version reported false coverage.** A quoted Commons full-text search for
  `"SH 2-1"` returned 20 files (a widefield rho Ophiuchi shot, an 1890s hymnal) and
  `wbsearchentities` returned the Heart Nebula for the same code. Both are printed as noise now;
  the count that decides is the Commons **category sitelink**, and a search hit only counts when
  the item really carries the designation in P528.
- The Commons API rate-limits anonymous bursts (a 429 killed the first run) — the same lesson as
  Wikidata, which is why the calls go through `audit.http`.

## Environment notes

- `python3 -m venv` still cannot create `.venv` on this mount; the venv is `/tmp/kilo/astrovenv`
  and pytest runs from the repo root (`pyproject.toml` sets `pythonpath`).
- Sesame resolves 25 names per request at ~2 s; MAST costs ~6 s per cone search, so a 261-target
  cross-check is a ~30 minute run — chunked and flushed, so a failure costs 25 targets, not all.
- SIMBAD direct is still blocked; nothing in the chain needs it, because Sesame resolves
  server-side.

## Session 2 — the dataset, and what real data broke

Same day, later. The user asked for a real download into the project folder (`data/`, now
gitignored) and for a resumable script rather than a 2 GB blocking fetch. The measured need was
**40 MB**: the pointed products for this catalogue are per-visit WFC3/IR drizzles, 13.3 MB each.

1. **Which observation actually images the nebula** — the §6.3 cone result was misleading. At a
   0.005 deg cone, `SH 2-7` returns two bias frames; at 0.1 deg it returns 44 observations. The
   decisive number is the **pointing separation** (`s_ra`/`s_dec`) against the **instrument
   footprint**: `SH 2-7`'s closest is 3.84' in a 29" ACS/HRC field, `SH 2-285`'s is 2.44' in a 37"
   WFPC2/PC field — all outside. Only `SH 2-252 F` has a pointing inside the field (WFC3/IR, 2.7'
   across, 0.74' away), with F105W/F125W/F160W at 1606–2206 s each.
2. **And that one is not a gap.** The header says `TARGNAME = NGC 2174`, HST program 13623. NGC 2174
   has a lead image on enwiki, ten+ files on Commons including a JWST one, and amateur SHO
   composites. The Wikidata item (Q88634040) holds only `SH 2-252 F`, so neither the P18 test nor
   the §6.2 cross-identification saw it. **All six pointed candidates are false positives**, and
   that is the real §6.3 finding: an archive cone search plus an instrument-name filter is not a
   coverage-gap detector.
3. **The data is still the right test set** — plan §0.C's "reprocess the same public FITS" mode:
   licence-clean, three aligned filters, and an object with a known published answer to compare
   against. `data/SH2-252F/` holds six files (two visits x three filters) plus `manifest.csv` with
   sha256, byte counts, retrieval time and header provenance. `examples/ngc2174_wfc3ir.toml` runs it.
4. **`experiments/fetch_data.py`** (new): MAST's product-listing service failed for *every*
   observation all session (`varchar to bigint`, server-side), and so `download_products`; the
   Download service is fine, and the per-visit naming convention is fixed, so the script builds
   `mast:HST/product/<obsid>/<obsid>_{drc,drz}.fits` URIs, probes with a 1-byte Range, resumes
   partial transfers, and reads provenance from the header.
5. **Real data then broke six things in the reference implementation**, none of which the synthetic
   scene can find because it has no blank coverage and no units:
   - `state`: the median/span metric was NaN (1.2 % NaN pixels), and `NaN > threshold` is False, so a
     stretched product would have been accepted as linear. All statistics now run on the finite
     subset and the invalid fraction is reported.
   - `state`: with the NaN excluded, a **linear** drizzle read as *stretched* (0.245 vs 0.02). A
     pipeline product with a physical `BUNIT` is now linear by construction; the header outranks the
     histogram and the disagreement is in the report (§7.1 rewritten accordingly).
   - `verify`: star apertures reaching into blank coverage gave NaN fluxes, so the whole R/B report
     printed `nan, nan` on a normal frame. Such stars are now dropped rather than zero-filled.
   - `stretch.auto_params`: `high_point` became NaN, which turns the entire composite blank. Now
     NaN-safe.
   - `config.build_stretch_params`: a `[stretch]` block that sets only `background_level` silently
     shipped `shadow_clip=0, high_point=1` — defaults in pixel units, nonsense in electrons/s, and
     nothing in the log said so. Auto is now per key. On this dataset the auto choice is
     `shadow_clip=0.0553, high_point=2.44`, and the banding metric improved from 2.36 (CHECK) to
     0.64 (ok).
   - `export`: `np.clip` does not touch NaN, so the 8/16-bit casts wrote garbage. Blank coverage is
     now black, on purpose and recorded.
   - `cli verify` never had a positional config argument, so the subcommand could not be invoked at
     all; and `out_dir` was resolved against the shell's cwd while inputs were resolved against the
     config, so the first run wrote 21 MB of output to `/media/sf_1/data/`, outside the project.
6. **Validation**: 104 tests pass (was 96; eight new, one per defect above plus the out_dir path
   rule). The full chain ran on real data: registration offsets 0.169 / 0.003 px, sky-match gains
   0.748 / 1.286, orientation 35 deg off north-up, star colour R/B median 1.05 with 44 % blue and
   42 % red stars, banding ok, 1.4 % of the frame is blank coverage.

**What the dataset is not:** a showcase. F105W/F125W/F160W is dust continuum, not H-alpha, and the
frame is 97.7 % sky: 2.3 % of pixels are above 3 sigma, 0.1 % above 30 sigma. It is a correctness
test, which is what it was fetched for.

## Next step suggestion

Rewrite §6.3 around what the run proved: a coverage-gap detector needs pointing separation versus
instrument footprint, the target's real name from the *archive header* (not only P528), and a
Commons category check — in that order, before the score. Then pick a target class where
archaeological depth is not the issue: a **recently released multi-filter set on an object that has
no composite** (§6.4 method 4, §5.3 infrared), enumerated from the archive rather than from
Wikidata, since the Wikidata-catalogue axis is now measurably exhausted for Sharpless. For the
dataset in hand, the outstanding §13.1 fields are the human ones: licence text verbatim (§4.2), the
survey reference for §7.6 (`ps1.stsci.edu` and `aladin.cds.unistra.fr` were both blocked this
session — retry, or use a Gaia DR2 cutout for the star-colour check), and the operator name.
