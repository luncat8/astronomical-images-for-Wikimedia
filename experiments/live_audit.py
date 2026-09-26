"""Live Wikidata coverage audit (plan §6.2, entry point 0.B) — the real network run.

The offline tests prove the logic; only this script proves the *numbers*. It measures
the gap count per catalogue through both enumeration paths, prints a shortlist, and runs
the §6.3 MAST cross-check on the few targets that do carry coordinates. Requires network
access to wikidata.org and mast.stsci.edu, and astropy/astroquery for the last section.

	experiments/live_audit.py [shortlist_size]
"""

import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

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


def mast_section():
	"""§6.3 cross-check. M31/M33 stand in for the real shortlist: catalogue stubs carry no
	coordinates at all (0 of 327 Sharpless entries), so this is the shape of the check, not
	the check itself — a name resolver has to run first."""
	from astroproc.audit.mast import coverage

	targets = HERE / "out" / "mast-targets.csv"
	targets.parent.mkdir(parents=True, exist_ok=True)
	targets.write_text("name,ra,dec\nM31,44.95,40.383333\nM33,31.433333,-26.483333\n", encoding="utf-8")
	print("\nMAST observation coverage (astroquery, live)")
	print(coverage(targets))


def guarded(label, work):
	"""One flaky endpoint must not truncate the table this script exists to produce."""
	try:
		return work()
	except Exception as exc:
		return f"  FAILED  {type(exc).__name__}: {exc}"


def main():
	size = int(sys.argv[1]) if len(sys.argv) > 1 else 10
	print("gap counts per catalogue, live Wikidata")
	for prefix, p31 in CATALOGUES:
		print(guarded(repr(prefix), lambda: count_row(prefix, p31)))
	shortlist("SH 2-", HII_REGION, size)
	shortlist("RCW", None, size)
	mast_section()


if __name__ == "__main__":
	main()
