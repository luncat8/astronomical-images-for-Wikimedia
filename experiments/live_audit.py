"""Live coverage audit chain (plan §6.2 + §6.3, entry point 0.B) — the real network run.

The offline tests prove the logic; only this script proves the *numbers*. It measures the gap
count per catalogue through both enumeration paths, prints shortlists, resolves the Sharpless
gaps to coordinates (catalogue stubs carry none) and runs the §6.3 archive cross-check on them.
Needs wikidata.org, vizier.cds.unistra.fr and mast.stsci.edu, plus astropy/astroquery for the
coverage section.

	experiments/live_audit.py [shortlist_size] [cone_radius_deg]
"""

import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from astroproc.audit.coords import resolve_gaps  # noqa: E402
from astroproc.audit.mast import coverage  # noqa: E402
from astroproc.audit.sparql import gap_count, missing_p18  # noqa: E402

HII_REGION = "Q11282"          # the P31 anchor that makes a STRSTARTS filter affordable
CATALOGUES = [
	("Sh2", None),             # index path: only the hyphenated spellings are reachable
	("Sh2", HII_REGION),
	("SH 2-", HII_REGION),     # anchored path: the space-separated spellings
	("RCW", None),
	("Coll", None),
	("Cald", None),
	("Abell", None),
	("NGC", None),
	("IC", None),
	("UGC", None),
	("PGC", None),
]
OUT = HERE / "out"
# TESS sectors and GALEX tiles cover the whole sky, so "some data exists" is true for almost
# every target and says nothing. What separates a candidate from the rest is a pointed
# observation: HST, JWST, or a filter set with more colour in it than a survey.
POINTED = ("HST", "JWST", "WFC3", "ACS", "NIRC", "NIRCam", "WFPC2")
CHUNK = 25


def count_row(prefix, p31):
	start = time.time()
	total = gap_count(prefix, p31=p31)
	how = f"class {p31}" if p31 else "search index"
	return f"{prefix!r:>9}  gaps={total:>6}  {how:<13} {time.time() - start:5.1f}s"


def shortlist(prefix, p31, size):
	rows, total = guarded("shortlist", lambda: missing_p18(prefix, limit=size, p31=p31))
	if isinstance(rows, str):
		print(f"\n{prefix!r} (class {p31 or 'index'}): {rows}")
		return
	print(f"\n{prefix!r} (class {p31 or 'index'}): {total} gaps, {len(rows)} shown")
	for row in rows:
		coords = f"{row['ra']:.5f} {row['dec']:+.5f}" if "ra" in row else "no coordinates"
		aliases = f"  also: {', '.join(row['aliases'][:4])}" if row["aliases"] else ""
		print(f"  {row['item']}  {row['label'] or '-':<28} [{'; '.join(row['codes'])}]{aliases}  {coords}")


def coverage_section(radius_deg):
	"""§6.3 on the real shortlist: gaps -> coordinates -> archive cone search."""
	from astroproc.audit.coords import write_targets

	OUT.mkdir(parents=True, exist_ok=True)
	targets = OUT / "sharpless-coords.csv"
	rows, total = guarded("resolve", lambda: resolve_gaps("SH 2-", p31=HII_REGION, limit=300))
	if isinstance(rows, str):
		print(f"\nMAST cross-check skipped: {rows}")
		return
	write_targets(rows, targets)
	resolved = [row for row in rows if row["ra"] is not None]
	print(f"\nresolved {len(resolved)} of {total} Sharpless gaps -> {targets}")
	types = Counter(row["otype"] or "?" for row in resolved)
	print(f"types: {', '.join(f'{otype}={n}' for otype, n in types.most_common(6))}")
	print(f"unresolved: {', '.join(r['name'] for r in rows if r['ra'] is None) or 'none'}")

	print(f"\nMAST coverage at {radius_deg} deg, {len(resolved)} cone searches, live")
	instruments, hits = Counter(), 0
	pointed = []
	for start in range(0, len(resolved), CHUNK):
		chunk = resolved[start:start + CHUNK]
		table = guarded(f"chunk {start}", lambda: coverage(chunk, radius_deg=radius_deg))
		if isinstance(table, str):
			print(f"  {table}")
			continue
		for row in table:
			instruments.update(name for name in row["instruments"].split(",") if name != "-")
			hits += 1 if row["n_obs"] > 0 else 0
			if any(name in POINTED for name in row["instruments"].split(",")):
				pointed.append((row["target"], row["n_obs"], row["instruments"], row["filters"]))
		print(f"  {min(start + CHUNK, len(resolved))}/{len(resolved)} checked", flush=True)

	print(f"targets with any imaging: {hits}/{len(resolved)}")
	print(f"instruments seen: {instruments.most_common()}")
	print(f"pointed observations (HST/JWST): {len(pointed)}")
	for target, n_obs, names, filters in pointed:
		print(f"  {target:<10} {n_obs:>4} obs  {names[:70]:<70} {filters[:60]}")


def guarded(label, work):
	"""One flaky endpoint must not truncate the table this script exists to produce."""
	try:
		return work()
	except Exception as exc:
		return f"  FAILED  {label}  {type(exc).__name__}: {exc}"


def main():
	size = int(sys.argv[1]) if len(sys.argv) > 1 else 10
	radius = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1
	print("gap counts per catalogue, live Wikidata")
	for prefix, p31 in CATALOGUES:
		print(guarded(repr(prefix), lambda: count_row(prefix, p31)))
	shortlist("SH 2-", HII_REGION, size)
	shortlist("RCW", None, size)
	coverage_section(radius)


if __name__ == "__main__":
	main()
