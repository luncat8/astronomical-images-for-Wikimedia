# Worklog — reference implementation of plan.md (§16)

Date: 2026-09-26
Branch: arena/01a0de0c-astronomical-images-for-wikime

## What was done

1. Read and reviewed `plan.md`; no policy or factual corrections needed (statements dated
   2026-09-26). Gaps were architectural, not factual: D3 (scripted chain) and D6 (batch audit)
   had no executable form.
2. Implemented `src/astroproc` per plan §7/§3.2/§6/§13.2 — see plan §16 for the module map and
   invariants (written to be fork-complete).
3. Test suite: 64 tests, synthetic scene with planted ground truth (star colour classes, skies,
   throughput, saturated star, TAN WCS). End-to-end assertion: planted blue/white/red stars read
   blue/white/red after the full pipeline.
4. CLI (`astroproc state|process|verify|audit`) exercised on the demo scene.
5. `experiments/demo_run.py` → demo SHO composite + auto-filled 21-line log (logs/demo-run.log);
   `experiments/stretch_perf.py` → 115 Mpixel/s at 4k², one scratch buffer
   (logs/stretch_perf.log).
6. plan.md updated: §0.9 pointer, D3/D6 marked resolved, new §16.
7. findings-pitfalls-skills.md: reusable pitfalls (NaN propagation via fractional powers and
   nan-median, einsum for channel-first luma, WCS mirror vs rotation, PIL fromarray, str.format
   vs SPARQL braces, batched-edit persistence).

## Validation

- `pytest -q`: 64 passed, 0 warnings.
- Demo run log complete: steps 1–18 filled, 19–21 carried as explicit TODOs (human fields).
- Orientation check reports N/E angles and handedness; mirror and rotation detected in tests.
- Banding/CA metrics: planted banding and fringing detected, clean scenes pass.
- Perf: stretch = one float32 scratch; background stats on a strided sample (~4 Mpx).

## Bugs found and fixed during implementation

- median-fraction metric initially degenerate (0 always) → percentile-anchored span metric.
- SHO gamma on sky-subtracted noise produced NaN → silently propagated to `high_point=nan`
  → floor at 0 before fractional powers (caught by the demo run, not by tests).
- Orientation north-vector x-component hardcoded 0 → rotation undetectable → tangent-plane
  offsets for both axes.
- `(3,H,W) @ (3,)` matmul invalid → einsum luma.
- PIL needed channel-last + deprecated mode arg → `_hwc` adapter, inferred mode.
- SPARQL braces vs `str.format` → escaped template.
- Banding metric was a no-op (np.median over all-NaN rows → NaN → 0) → nan-aware profiles with
  interpolation; CA threshold unreachable with Rec.709 luma → (R+B)/2−G edge-excess metric.

## Environment notes

- Sandbox network: only PyPI reachable (Wikimedia/SIMBAD/MAST/PS1 blocked). Network code is
  isolated at module edges and logic-validated offline; first real `astroproc audit sparql` /
  `mast` run needs an unblocked network — that is the natural next step.
- `.venv/` not persisted: recreate `python3 -m venv .venv && .venv/bin/pip install -e .[dev]`.

## Next step suggestion

Run the audit chain for real against Wikidata + MAST (network permitting): pick a catalogue
(e.g. Sharpless 2), `astroproc audit sparql --prefix "Sh2 "`, cross-check coverage with
`astroproc audit mast`, score the survivors with the §6.5 rubric, and take the first real
0.B target through `astroproc process` end to end — which then exercises §4 licence
identification on a live archive retrieval.
