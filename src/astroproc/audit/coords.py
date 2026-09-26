"""Designation -> ICRS coordinates: what the §6.3 archive cross-check needs and Wikidata cannot give.

Measured 2026-09-26: 0 of 327 Sharpless and 0 of 173 RCW entries carry P625, so the coverage
audit (§6.2) necessarily ends at designations and cannot become an archive cone search on its
own. Sesame — the CDS resolver astropy's `SkyCoord.from_name` also uses — answers a whole batch
of names per request and names the catalogue that answered, which keeps each position's
provenance visible: a cone search is only as good as the position at its centre, and a survey
catalogue position and a SIMBAD position are not interchangeable evidence.

Designation spellings are inconsistent across catalogues and across Wikidata items ("Sh2-29",
"SH2-8", "SH 2-104"), so a name that fails is retried with the cross-identifications the audit
already collected. §6.2 demands cross-identifying before believing a gap; the same alias set is
what rescues the position, and the `via` column records which name answered.
"""

import csv
import sys
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

from .http import request

# vizier.cds.unistra.fr answers and redirects the cgi-bin path to cds.unistra.fr; the sesame
# host itself (cds.unistra.fr/sesame/) is not served on this network. SNV = SIMBAD, NED and
# VizieR in that order, and the answer carries one <Target> per name with a position and an
# identifier per database that knew it.
SESAME_URL = "https://vizier.cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV"
BATCH = 25
MAX_ALIASES = 3
# `audit mast` reads name,ra,dec; the rest is provenance and is ignored there.
TARGET_COLUMNS = ("name", "ra", "dec", "source", "object", "otype", "via")
DESIGNATION_COLUMNS = ("designation", "name", "codes")


def resolve_gaps(prefix, p31=None, limit=200, timeout=60, use_aliases=True):
	"""Wikidata gap shortlist -> rows with coordinates, plus the true gap total.

	The shortlist may be shorter than the total; the total keeps that truncation visible.
	"""
	from .sparql import missing_p18

	rows, total = missing_p18(prefix, limit=limit, p31=p31)
	return _attach_coordinates(rows, timeout, use_aliases), total


def resolve_names(names, timeout=60, batch=BATCH):
	"""One row per name, resolved or not, in the order asked. Alias fallback is the caller's job."""
	names = list(names)
	found = {}
	for start in range(0, len(names), batch):
		found.update(parse_sesame(_query(names[start:start + batch], timeout)))
	# keyed on the stripped echo, because Sesame returns the name it was given, not the one asked for
	found = {echoed.strip(): row for echoed, row in found.items()}
	return [_row(name, found.get(name.strip())) for name in names]


def resolve_csv(csv_path, timeout=60, use_aliases=True):
	"""Rows for a designation CSV — the output of `audit sparql --out` or a hand-made list."""
	return _attach_coordinates(_read_designations(csv_path), timeout, use_aliases)


def parse_sesame(text):
	"""Sesame XML -> {queried name: {ra, dec, source, object, otype}}.

	A Target carries one Resolver per database consulted and one position per Resolver; the first
	with a position wins, because Sesame only consults the next database when the previous one
	does not know the name. A name nothing knows keeps its Target with no Resolver at all, and
	that empty result is the answer — it is recorded, not dropped.
	"""
	rows = {}
	for target in ElementTree.fromstring(text).iter("Target"):
		name = _text(target, "name")
		if not name:
			continue
		rows[name] = _target_row(target)
	return rows


def write_targets(rows, path="-"):
	"""Write the `name,ra,dec` CSV that `astroproc audit mast` consumes, provenance included.

	`-` means stdout, so the chain pipes: `audit coords --prefix ... | ...`. The human summary
	goes to stderr and leaves the CSV a clean pipe.
	"""
	stream = sys.stdout if path == "-" else Path(path).open("w", newline="", encoding="utf-8")
	writer = csv.DictWriter(stream, fieldnames=list(TARGET_COLUMNS), extrasaction="ignore")
	writer.writeheader()
	writer.writerows(rows)
	if stream is not sys.stdout:
		stream.close()
	return path


def _target_row(target):
	"""First resolver position of one Target, or an empty position if none answered."""
	empty = {"ra": None, "dec": None, "source": "", "object": "", "otype": ""}
	for resolver in target.iter("Resolver"):
		ra, dec = _text(resolver, "jradeg"), _text(resolver, "jdedeg")
		if not ra or not dec:
			continue
		return {
			"ra": float(ra),
			"dec": float(dec),
			"source": resolver.get("name", ""),
			"object": _text(resolver, "oname"),
			"otype": _text(resolver, "otype"),
		}
	return empty


def _attach_coordinates(rows, timeout, use_aliases=True):
	"""Resolve each row's own designation, then its aliases for the ones that failed."""
	out = []
	for row, resolved in zip(rows, resolve_names([_designation(row) for row in rows], timeout)):
		out.append(_row_with(row, resolved))
	if not use_aliases:
		return out
	return _fill_from_aliases(out, timeout)


def _fill_from_aliases(rows, timeout):
	"""One batched pass over the aliases of the unresolved rows; the first alias that answers wins."""
	waiting = {row["name"]: row for row in rows if row["ra"] is None and row["aliases"]}
	pairs = [(row, alias) for row in waiting.values() for alias in row["aliases"][:MAX_ALIASES]]
	if not pairs:
		return rows
	for (row, _), candidate in zip(pairs, resolve_names([alias for _, alias in pairs], timeout)):
		if candidate["ra"] is None or row["name"] not in waiting:
			continue
		row.update(ra=candidate["ra"], dec=candidate["dec"], source=candidate["source"],
			object=candidate["object"], otype=candidate["otype"], via=candidate["name"])
		del waiting[row["name"]]
	return rows


def _query(names, timeout):
	"""One Sesame request for a batch of names: a bare query string, one valueless parameter each.

	`?Sh2-104&RCW%205` is the batch form. `Name=Sh2-104` and `Sh2-104=` both resolve to nothing
	*silently* — Sesame reads the whole `key=value` as the name and answers a well-formed
	"nothing found" document, so a wrong URL looks exactly like a catalogue that does not
	exist. Hence the hand-built query string instead of a params dict, which always emits `=`.
	"""
	query = "&".join(quote(name, safe="") for name in names)
	return request("GET", f"{SESAME_URL}?{query}", timeout=timeout).text


def _read_designations(csv_path):
	"""Rows of {name, aliases} from a designation CSV, keeping aliases for the retry pass.

	Accepts both shapes the chain produces: a `designation` column, optionally with an
	`aliases` column beside it (`audit sparql --out`), or a single cell holding several
	designations separated by `;`.
	"""
	reader = csv.DictReader(Path(csv_path).open(encoding="utf-8"))
	columns = reader.fieldnames or []
	column = next((name for name in DESIGNATION_COLUMNS if name in columns), None)
	if column is None:
		raise SystemExit(f"{csv_path} needs one of these columns: {', '.join(DESIGNATION_COLUMNS)}")
	rows = []
	for record in reader:
		codes = _split_codes(record.get(column, ""))
		others = _split_codes(record.get("aliases", "")) if "aliases" in columns else []
		names = codes + [alias for alias in others if alias not in codes]
		if not names:
			continue
		rows.append({"name": names[0], "aliases": names[1:]})
	return rows


def _split_codes(cell):
	return [code.strip() for code in cell.replace(",", ";").split(";") if code.strip()]


def _designation(row):
	"""The name to resolve: the matching code of an audit row, or the name of a CSV row."""
	return row["codes"][0] if row.get("codes") else row["name"]


def _row(name, found):
	"""`via` is the name that produced the position: itself, the alias that rescued it, or empty."""
	position = found or {}
	row = {key: position.get(key) for key in ("ra", "dec", "source", "object", "otype")}
	row.update(name=name, via=name if row["ra"] is not None else "")
	return row


def _row_with(source_row, resolved):
	"""Keep the Wikidata row's own designation as the name, so the CSV joins back to the audit.

	`aliases` stays on the row for the retry pass and is dropped when the CSV is written.
	"""
	row = {key: resolved[key] for key in ("ra", "dec", "source", "object", "otype", "via")}
	row.update(name=_designation(source_row), aliases=list(source_row.get("aliases", [])))
	return row


def _text(element, tag):
	node = element.find(tag)
	return "" if node is None or node.text is None else node.text.strip()
