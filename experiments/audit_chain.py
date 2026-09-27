"""The audit tail replayed offline (plan §6.3 tests 1-4, §16.4) — the chain, without the network.

`experiments/live_audit.py` is the real half and needs Wikidata, Sesame and MAST. This script fixes
the three endpoints it cannot reach from the sandbox and runs the same commands, so what the
operator *sees* can be reviewed: which verdicts are answers, which are counted non-answers, and what
the two modes of `audit commons` do to the same gap list. The fixtures are the 2026-09-26 objects —
`SH 2-252 F` (imaged, but the archive calls it NGC-2174), `SH 2-7` (a G0 article with no lead image
whose nearest HST pointing is 8 fields off), `SH 2-20` (a P18 "gap" already illustrated as `RCW
141`), and a recently public two-filter WFC3/IR set.

	experiments/audit_chain.py            # writes experiments/logs/audit-chain.log
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from astroproc import cli  # noqa: E402
from astroproc.audit import commons, mast  # noqa: E402

OUT = HERE / "out" / "audit-chain"
LOG = HERE / "logs" / "audit-chain.log"

# The coordinates the resolver returned for four of the 261 Sharpless gaps of 2026-09-26, and the
# fifth for the twelve it could not resolve (lettered sub-components of a region SIMBAD knows whole).
TARGETS = """name,ra,dec,source,object,otype,via
SH 2-252 F,92.2930,20.4800,Sc=Simbad,NGC 2174,HII,SH 2-252 F
SH 2-7,83.0,-4.0,Sc=Simbad,SH  2-7,HII,SH 2-7
SH 2-20,94.5867,20.7061,Sc=Simbad,RCW 141,HII,SH 2-20
SH 2-289,88.5931,-6.5711,Sc=Simbad,SH  2-289,HII,SH 2-289
SH 2-106 A,,,Sc=Simbad,,,
"""

GAPS = """designation,aliases,item,label,ra,dec
SH 2-252 F;NGC 2174,NGC 2174,Q639464,NGC 2174,92.293,20.48
SH 2-7,RCW 11,Q88634040,Sh 2-7,83.0,-4.0
SH 2-20,RCW 141,Q1,,94.5867,20.7061
SH 2-289,,Q2,,88.5931,-6.5711
"""


def box(ra, dec, arcsec):
	"""A square footprint of `arcsec` on the sky — MAST's own form, size in RA/Dec degrees."""
	half_ra = arcsec / 7200 / math.cos(math.radians(dec))
	half_dec = arcsec / 7200
	return (f"POLYGON {ra - half_ra} {dec + half_dec} {ra + half_ra} {dec + half_dec} "
		f"{ra + half_ra} {dec - half_dec} {ra - half_ra} {dec - half_dec} {ra - half_ra} {dec + half_dec}")


def observation(**kwargs):
	row = {"collection": "HST", "instrument": "WFC3/IR", "filters": "F105W", "obs_id": "ichx02020",
		"target_name": "NGC-2174", "region": box(92.2930, 20.4800, 187), "proposal": "13623",
		"pi": "Levay, Zolt", "public": "2014-05-19", "exptime": "1202.9", "rights": "PUBLIC"}
	return {**row, **kwargs}


# The cone-search answers for the whole fixture, as the archive returned them (or would have).
CONE = [
	# SH 2-252 F / NGC 2174: three WFC3/IR filters of one program, all covering the object.
	observation(filters="F105W", exptime="1202.9"),
	observation(filters="F125W", obs_id="ichx02030", exptime="1402.9"),
	observation(filters="F160W", obs_id="ichx02040", exptime="2602.9"),
	# SH 2-7: a 29" ACS/HRC frame 3.84' away — the pointing that does not image the object, which
	# is why its Commons check (a G0 article with no lead image) is invisible to the default chain.
	observation(instrument="ACS", filters="F814W", obs_id="j8ga01hzq", target_name="SH-2-7",
		region=box(83.0, -4.064, 29), proposal="10775", pi="PI", public="2006-08-01", exptime="1200"),
	# SH 2-20 / RCW 141: a real HST pointing, and the Commons file is already there.
	observation(instrument="ACS/WFC", filters="F606W;F814W", obs_id="o6d601", target_name="RCW-141",
		region=box(94.5867, 20.7061, 202), proposal="10775", pi="PI", public="2006-08-01",
		exptime="1200.0"),
	# SH 2-289: a two-filter WFC3/IR set released in 2025 — the archive-first opportunity (§6.3).
	observation(filters="F110W", obs_id="new02010", target_name="SH-2-289", region=box(88.5931, -6.5711, 187),
		proposal="17500", pi="Someone", public="2025-09-01", exptime="900.0"),
	observation(filters="F160W", obs_id="new02020", target_name="SH-2-289", region=box(88.5931, -6.5711, 187),
		proposal="17500", pi="Someone", public="2025-09-01", exptime="900.0"),
]


def cone(coord, radius_deg, collections):
	"""The fixture as a cone search: only the rows near this target, so the counts are per target."""
	from astropy.coordinates import SkyCoord
	from astroproc.audit import footprint

	near = []
	for row in CONE:
		kind, geometry = footprint.parse(row["region"])
		if kind is None:
			continue
		centre = geometry[0] if kind == "CIRCLE" else geometry.mean(axis=0)
		if coord.separation(SkyCoord(*centre, unit="deg", frame="icrs")).deg <= radius_deg:
			near.append(row)
	return near


def wikidata(qid):
	"""One `wbgetentities` entry per fixture item: codes, category sitelink, article."""
	items = {
		"Q639464": (("SH 2-252 F", "NGC 2174"), "Category:NGC 2174", "NGC 2174"),
		"Q88634040": (("SH 2-7",), "", "Sh 2-7"),
		"Q1": (("SH 2-20", "RCW 141"), "Category:RCW 141", "RCW 141"),
		"Q2": (("SH 2-289",), "", ""),
	}
	codes, category, article = items[qid]
	entry = {"id": qid, "claims": {"P528": [{"mainsnak": {"datavalue": {"value": code}}} for code in codes]},
		"sitelinks": {"enwiki": {"title": article}} if article else {}}
	if category:
		entry["sitelinks"]["commonswiki"] = {"title": category}
	return entry


def fake_get(url, **params):
	"""The three APIs, from the fixture, including the full-text noise a real search returns."""
	if url == commons.WIKIDATA:
		return {"entities": {row["id"]: row for row in map(wikidata, ("Q639464", "Q88634040", "Q1", "Q2"))}}
	if url == commons.ENWIKI:
		# `Sh 2-7` has an article and no lead image: the purest G0, and invisible to P18 (§6.3.1).
		leads = {"NGC 2174": "https://upload.wikimedia.org/NGC2174.jpg",
			"RCW 141": "https://upload.wikimedia.org/RCW141.jpg"}
		image = leads.get(params.get("titles", ""))
		return {"query": {"pages": {"1": {"original": {"source": image}} if image else {}}}}
	if params.get("list") == "categorymembers":
		return {"query": {"categorymembers": [{"title": "File:NGC 2174 Hubble.jpg"},
			{"title": "File:RCW 141.jpg"}]}}
	return {"query": {"search": [{"title": "File:Rho Ophiuchi widefield.jpg"},
		{"title": "File:Hymnal, page 22.jpg"}]}}


def section(title):
	print(f"\n{'=' * 4} {title}\n")


def main():
	OUT.mkdir(parents=True, exist_ok=True)
	mast._cone = cone  # the fixture replaces the network
	commons.get = fake_get
	targets = OUT / "coords.csv"
	targets.write_text(TARGETS, encoding="utf-8")
	gaps = OUT / "gaps.csv"
	gaps.write_text(GAPS, encoding="utf-8")

	section("audit pointed: what the archive calls each target, and did it land on it (tests 1-2)")
	cli.main(["audit", "pointed", str(targets), "--out", str(OUT / "pointed.csv")])
	section("audit sets: pointed + covering + multi-filter + newly public (tests 1-3)")
	cli.main(["audit", "sets", str(targets), "--min-filters", "2", "--since", "2024-01-01",
		"--out", str(OUT / "sets.csv")])
	section("audit commons: only the designations the archive answered for (default)")
	cli.main(["audit", "commons", str(gaps), "--targets", str(OUT / "pointed.csv"),
		"--out", str(OUT / "candidates.csv")])
	section("audit commons --all-targets: a curated shortlist is taken as given")
	cli.main(["audit", "commons", str(gaps), "--targets", str(OUT / "pointed.csv"),
		"--all-targets", "--out", str(OUT / "candidates-all.csv")])
	section("audit score SH 2-7: the three machine rows filled, the seven human ones visible")
	cli.main(["audit", "score", str(OUT / "candidates-all.csv"), "--designation", "SH 2-7",
		"--set", "3=3", "--set", "4=2", "--set", "5=3", "--set", "6=3", "--set", "7=2", "--set", "8=1",
		"--set", "9=2", "--set", "10=2"])
	cli.main(["audit", "score", str(OUT / "candidates-all.csv"), "--out", str(OUT / "dossiers.txt")])
	print(f"\nartifacts in {OUT}")


if __name__ == "__main__":
	with LOG.open("w", encoding="utf-8") as handle:
		saved, sys.stdout = sys.stdout, handle
		try:
			main()
		finally:
			sys.stdout = saved
	print(f"wrote {LOG}")
