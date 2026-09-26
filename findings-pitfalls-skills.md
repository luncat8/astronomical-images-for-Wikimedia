# Findings, pitfalls, skills

Notes for LLM agents working in this repo. Reusable lessons only; implementation specifics live in plan.md §16 and archive/.

## Sandbox / environment

- Only pypi.org is reliably reachable; Wikimedia, SIMBAD, MAST, PS1 and other astronomy endpoints are blocked at network level. Build network-touching code against the real APIs but keep I/O isolated at module edges (e.g. `audit/sparql.py` separates `missing_p18` from `parse_response`), and validate logic offline with synthetic data.
- `.venv/` in the repo root is excluded from session snapshots. Recreate with `python3 -m venv .venv && .venv/bin/pip install -e .[dev]` after resuming; keep `pyproject.toml` authoritative.
- `git push` may fail with "Invalid username or token" — expected, user applies manually (AGENTS.md).

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

- SPARQL queries built with `str.format` need every literal brace escaped (`{{ }}`) — SPARQL is brace-dense, so consider `string.Template` or replacement next time.

## Testing pipeline code

- A synthetic scene with planted ground truth (star colour classes, sky levels per channel, throughput factors, one saturated star, TAN WCS) pays for itself many times over: it caught NaN propagation, a no-op metric, a matmul misuse, mirror/rotation bugs, and it doubles as the demo generator.
- Assert log *completeness* (every template line either filled or visibly `<TODO>`), not just absence of exceptions — the log is a deliverable (plan §7.9, §13.2).
