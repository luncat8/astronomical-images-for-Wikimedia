# Worklog — the audit chain's tail: sets, commons, score (§6.3, §6.5, §13.1)

Date: 2026-09-27
Branch: arena/01a0e4eb-astronomical-images-for-wikime
Started from: the next-step suggestion of `2026-09-26-resolver-and-archive-crosscheck-worklog.md`

## What was done

1. Closed the three promises the previous session's code made and did not keep:
   `mast.write_pointed` says its CSV is "the file `audit commons` and the rubric read next", and
   neither `audit commons` nor `audit score` existed as a command; `score.py` had a rubric and a
   dossier renderer that nothing called. The 0.B loop now runs end to end as commands, each writing
   the file the next one reads.
2. **`audit sets`** — new module `audit/sets.py`, the archive-first axis of plan §6.4 method 4 with
   the timeliness axis built in (§6.3). A set is one program's pointing with one detector
   (`collection`, `instrument`, `proposal`, archive target name); it is a colour set when its
   distinct filters reach `--min-filters`, its footprints cover the object, and its last exposure
   became public on or after `--since`. Six verdicts keep the non-answers apart:
   `fewer_filters_than_requested`, `released_before_window`, `footprint_missed`,
   `footprint_unreadable`, `no_pointed_data`, `no_coordinates`.
3. **`audit commons`** — `commons.candidates` joins the `audit sparql` gap shortlist to the rows
   `audit pointed`/`audit sets` answered for, matches on every code and cross-identification, and
   classifies the gap: `covered`, `G0 (article without a lead image)`, `G0 (no article, notability
   unproven)`. `--all-targets` overrules the filter for a curated shortlist, because a target the
   HST pointings missed is still a candidate for a ground-based archive.
4. **`audit score`** — `score.auto_fill` answers exactly the three rows the audit row can decide
   (1 licence from the archive's rights field, 2 the gap, 9 feasibility) and leaves the other seven
   visibly unscored; `profile` fills the §13.1 dossier from the candidate row and marks the rest
   `<TODO>`; `--set ROW=VALUE` lets the operator complete a rubric and get a real verdict.
5. Corrected the two claims the plan and `mast.py` made about the 2026-09-26 numbers (the six
   name-matched pointed candidates were "all false positives"; §6.3.1 in fact records one already
   illustrated under another name and two G0 articles) and rewrote §6.3 around the four tests in
   their order, with the archive-first and Commons variants as subsections after the measurements.
6. plan.md: §0.9 and §1 0.B carry the ordered chain; new §6.3 h4s; §16.1 gained `footprint.py`,
   `commons.py` and `sets.py` rows and a corrected `cli.py` row; §16.4 describes the audit tests and
   the two chain blocks. findings-pitfalls-skills.md gained the audit-chain lessons.

## Validation

- `pytest -q`: 163 tests, 1 warning from an unrelated astropy sigma-clip on NaN input (was 128).
  New: `tests/test_sets.py` (12), `tests/test_chain.py` (7 — the CLI driving commons → score over
  real CSV files), and the commons/score additions.
- `experiments/audit_chain.py` replays the whole tail offline against the 2026-09-26 fixtures and
  writes `experiments/logs/audit-chain.log`: pointed (`SH 2-252 F` imaged as `NGC-2174`; `SH 2-7`
  215.9" outside a 29" frame), sets (one 2025 two-filter set for `SH 2-289`, two older sets
  reported as `released_before_window`), commons (default: 3 of 4 gaps checked, `SH 2-20` covered as
  `RCW 141`; `--all-targets`: 4 checked, `SH 2-7` reads `G0 (article without a lead image)` while the
  archive's own verdict is `footprint_missed`), score (`SH 2-7`: rows 1/2/9 filled by the machine,
  24/30 → pursue after seven operator rows).
- Artifacts written: `experiments/out/audit-chain/{pointed,sets,candidates,candidates-all}.csv` and
  `dossiers.txt`.

## Bugs found and fixed during implementation

- **`wbgetentities` caps `ids` at 50.** `commons.entity` sent one request for the whole shortlist, so
  a 274-row audit would have answered with the first 50 and no error — a silent "most gaps are
  covered". Batched, with a test that pins the batch sizes.
- **A field that only exists after the CSV writer is a field the terminal formatter does not have.**
  `n_category_files` was computed inside `write_candidates`, so `audit commons` printing its own
  rows raised `KeyError` on the first row. The count now belongs to the row (`candidates`), and the
  writer only joins lists.
- **`audit sets` reported "missed" for a target the archive never aimed at.** When no pointed
  imaging row was left after the role filter, the empty verdict was `footprint_missed` — a claim
  about an observation that does not exist. `_empty_verdict` now distinguishes the four reasons
  (`unreadable` > `no_pointed_data` > `missed`), since each one sends the operator somewhere else.
- **A missed pointing's frame and filters were shown as the candidate's data.** In the dossier for
  `SH 2-7` the channels read `F814W` and the FOV `29x29` — the frame that misses the object by
  3.84'. `profile` now takes `channels`, `obs_id` and `fov` only when a footprint covers the object,
  and states the miss (with its separation) in the data-source line instead.
- **The answering verdicts were duplicated as string literals** in `score._covered` ("imaged") while
  `commons` had `ANSWER_VERDICTS`; the second verdict (`colour_set`) then did not count as covered.
  One tuple, imported.
- **The `otype` false-positive detector stopped at the resolver.** `audit coords` writes it,
  `audit pointed` dropped it, and the dossier showed an empty "Type:". It now travels through the
  pointed and sets rows into the candidate row.

## Design decisions worth keeping

- The archive audit's answers are the **shortlist filter by default** (`audit commons --targets`),
  because a 261-row audit dump costs 522 API calls for a question already answered; the escape hatch
  is explicit (`--all-targets`) and printed with the counts of both modes.
- A set is **one program with one detector**. Merging programs invents a composite nothing observed
  together; mixing detectors is the §7.4 alignment problem, and both sets stay visible in the output
  rather than being averaged into a filter list.
- An **unknown release date is not an old one**: such a set stays a colour set with an empty date,
  and the summary counts the rows the window removed instead of hiding them.
- Machine-filled rubric rows are limited to the three the evidence decides. A rubric filled in by the
  tool that produced the candidate is a rubric nobody read.

## Environment notes

- Network is still partial in this sandbox: pypi answered, everything astronomy-side (Wikidata, MAST,
  Sesame, Commons) timed out on 2026-09-27. All new logic is therefore validated offline with
  stubbed endpoints exactly as the previous sessions did; the live half is unchanged and still needs
  an unblocked host — `experiments/live_audit.py` for the numbers, and the four new commands for the
  tail.
- `/home/user/venv` (outside the repo) works: `python3 -m venv /home/user/venv && /home/user/venv/bin/pip install -e . pytest`.

## Next step suggestion

Run the tail live and record what it changes: `audit pointed` and `audit sets` on the 261 resolved
Sharpless gaps (expect the pointed list to shrink below six once the footprint test and the role
census both apply — the 2026-09-26 list came from a substring match on the instrument column), then
`audit commons --targets` on the survivors, and one `audit score` dossier for the best of them.
The two things the fixtures cannot settle are the ones that decide the first real upload: whether
`t_exptime` and `t_obs_release` are populated for HST/JWST imaging rows (the sets window depends on
the release date and the depth column), and whether MAST's `s_region` for JWST NIRCam mosaics is a
polygon per exposure or per association — the set grouping assumes the former. Fix whichever the
live answer contradicts, then take the winning candidate through `astroproc process`, which closes
the 0.B loop this worklog's chain now describes.
