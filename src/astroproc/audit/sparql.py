"""Wikidata coverage audit (plan §6.2, entry point 0.B): catalogue entries with no image.

Two enumeration paths, because neither Wikidata interface covers every catalogue on its own.

The search index (`haswbstatement:P528=<prefix>* -haswbstatement:P18`) is the cheap default:
measured live 2026-09-26, the plan's `FILTER(STRSTARTS(?cat, ...))` scan over `wdt:P528`
(41 402 entries for the NGC prefix alone) exceeds the 60 s WDQS budget and answers 504, while
`haswbstatement:P528=NGC*` returns in ~4 s. The index is also case-insensitive where STRSTARTS is
not — one nebula is filed as "Sh2-29", another as "SH2-8". It cannot do two things, both fatal for
whole catalogues: a wildcard only binds to the last token, so a space-separated code such as
"SH 2-104" is unreachable (`Sh2*` sees 6 items where `SH 2-*` would see hundreds), and it
token-matches, so the prefix "SH" also returns Shk, SHOC, SHARDS and SHBL objects.

A class-anchored SPARQL scan (`--class`) covers the space-separated spellings, because
`?item wdt:P31 wd:Q11282` is index-backed and the string filter then runs over one class only:
273 Sh2 entries with no P18 image, in 4 s, against 3 found through the index.

Both paths hand the same Q-ids to one batched detail pass, which adds what neither can: the rest
of the designation set (a gap under one code is often covered under another, §6.2) and
coordinates — which most catalogue stubs simply do not carry, so designations go on to the
resolver in `coords.py`, which is what the §6.3 archive cross-check consumes.

Both endpoints are flaky under load and the Action API rate-limits anonymous bursts, so every call
goes through `audit.http.request`, which retries a read timeout and honours `Retry-After` on a 429.
"""

import csv
from pathlib import Path

from .http import request

API = "https://www.wikidata.org/w/api.php"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "astroproc/0.1 (Wikimedia astronomy coverage audit; plan.md §6.2)"

GAP_SEARCH = "haswbstatement:P528={prefix}* -haswbstatement:P18"
GAP_COLUMNS = ("designation", "aliases", "item", "label", "ra", "dec")
PAGE = 50
SROFFSET_CAP = 10000
VALUES_BATCH = 60
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
MAX_SPLIT_DEPTH = 4

# "en,mul": catalogue stubs often have only a multilingual label (Q3928208 -> "RCW 114"),
# and without the fallback the label service silently answers with the bare Q-id.
DETAIL_QUERY = """SELECT ?item ?itemLabel ?cat ?coords WHERE {{
  VALUES ?item {{ {values} }}
  ?item wdt:P528 ?cat .
  OPTIONAL {{ ?item wdt:P625 ?coords . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
}}"""

# The anchor is the whole trick: STRSTARTS over all of wdt:P528 times out, over one class it does not.
CLASS_TAIL = """
  ?item wdt:P31 wd:{p31} .
  ?item wdt:P528 ?cat .
  FILTER(STRSTARTS(?cat, "{prefix}"))
  FILTER NOT EXISTS {{ ?item wdt:P18 ?img }}
"""

CLASS_COUNT_QUERY = "SELECT (COUNT(DISTINCT ?item) AS ?n) WHERE {{" + CLASS_TAIL + "}}"
CLASS_IDS_QUERY = (
	"SELECT DISTINCT ?item WHERE {{" + CLASS_TAIL + "}}\nORDER BY ?cat\nLIMIT {limit}"
)

def gap_count(prefix, timeout=60, p31=None):
	"""Number of catalogue entries with this prefix that carry no P18 image."""
	if p31:
		return _class_total(p31, prefix, timeout)
	return _search(prefix.strip(), offset=0, limit=1, timeout=timeout)["searchinfo"]["totalhits"]


def candidate_ids(prefix, limit=200, timeout=60, p31=None):
	"""Q-ids of gap entries for prefix, at most limit of them, plus the unpaginated total.

	The total is the honest size of the gap; the id list is a shortlist and may be shorter.
	Cross-identify every survivor (§6.2) before believing that no image exists.
	"""
	prefix = prefix.strip()
	if p31:
		return _class_candidate_ids(p31, prefix, limit, timeout)
	total = gap_count(prefix, timeout)
	ids, seen = [], set()
	for key in _search_keys(prefix, total, timeout):
		ids.extend(_collect(key, limit - len(ids), seen, timeout))
		if len(ids) >= limit:
			break
	return ids, total


def missing_p18(prefix, limit=200, timeout=60, p31=None):
	"""Rows of {item, label, codes, aliases, ra, dec}, one per entry, plus the gap total.

	ra/dec are absent when the entry has no P625 — the common case for catalogue stubs, and
	the reason a coordinate fallback (SIMBAD/VizieR by designation) belongs in the workflow.
	"""
	ids, total = candidate_ids(prefix, limit, timeout, p31)
	# The two paths filtered server-side by different rules, so the client guard must differ too.
	return parse_response(_detail_payload(ids, timeout), prefix=prefix, anchored=bool(p31)), total


def parse_response(payload, prefix="", anchored=False):
	"""One row per item: matching codes, every other code as an alias, coordinates if any.

	An item repeats once per designation it is known by (NGC 6334 also has RCW 127, GUM 62,
	SH2-8, ...), so the raw bindings are grouped here rather than reported as duplicates.
	Items with no matching code at all are dropped — the index can match a token of a code
	that no longer carries the prefix. `anchored` says which server-side rule produced the ids,
	because the detail pass hands back every code of every matched item and only the matching
	rule can tell a code from an alias.
	"""
	rows = {}
	for binding in payload["results"]["bindings"]:
		qid = binding["item"]["value"].rsplit("/", 1)[-1]
		row = rows.setdefault(qid, _row(qid, binding))
		code = binding.get("cat", {}).get("value", "")
		if _matches(code, prefix, anchored):
			row["codes"].append(code)
		else:
			row["aliases"].append(code)
		if "coords" in binding:
			row["ra"], row["dec"] = _point(binding["coords"]["value"])
	for row in rows.values():
		row["codes"] = sorted(row["codes"])
		row["aliases"] = sorted(row["aliases"])
	return sorted(
		(row for row in rows.values() if row["codes"]),
		key=lambda row: (row["codes"], row["item"]),
	)


def write_gaps(rows, path):
	"""Write the gap shortlist so the next step reads a file instead of the terminal.

	Columns: designation, aliases, item, label, ra, dec. `aliases` is the cross-identification
	set from the detail pass, which `coords.py` retries unresolved names with, so nothing the
	audit learned is lost between the two commands. A gap the entry already placed itself
	(rare, but P625 exists on some items) keeps those coordinates and is not re-resolved.
	"""
	records = [{
		"designation": ";".join(row["codes"]),
		"aliases": ";".join(row["aliases"]),
		"item": row["item"],
		"label": row["label"],
		"ra": row.get("ra", ""),
		"dec": row.get("dec", ""),
	} for row in rows]
	with Path(path).open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=list(GAP_COLUMNS))
		writer.writeheader()
		writer.writerows(records)
	return path


def parse_search(payload):
	"""Q-ids of one `list=search` page."""
	return [hit["title"] for hit in payload.get("search", [])]


def _matches(code, prefix, anchored=False):
	"""Does this designation belong to the prefix? The rule is the one the server used.

	Anchored (SPARQL `FILTER(STRSTARTS(?cat, "<prefix>"))`): the code must start with the prefix.
	That is exact, and the client guard has to be exact too — the looser token rule admits every
	"SH <n>-<m>" code, so a shortlist for "SH 2-" reported "SH 1-15" and "SH 1-5" under their own
	names when the server had matched them through the alias "SH 2-4" they also carry. An alias
	must be shown as an alias.

	Index (`haswbstatement:P528=<prefix>*`): the first token must start with the prefix, because
	that is what the search index matches on. Repeating its semantics instead of guessing at them
	keeps "Coll" covering "Collinder 69" (that is the token) and also "Collezione Ansaldi B 905"
	(that is what `Coll*` returns). Over-matching stays visible in the printed codes — a stricter
	rule here silently emptied a real shortlist, turning four Collinder gaps into zero rows.
	Narrow the prefix (`--prefix Collinder`) to cut the noise; §6.2.1 lists the collisions.
	"""
	if anchored:
		return code.strip().lower().startswith(prefix.strip().lower())
	return _token(code).startswith(_token(prefix.strip()))


def _token(text):
	return text.partition("-")[0].partition(" ")[0].lower()


def _search_keys(prefix, total, timeout, depth=0):
	"""Search keys covering prefix, each small enough to page through to the end.

	Partitioning needs a single-token prefix: a wildcard binds to the last token only, so
	"NGC" can be split into "NGC0", "NGC1", ... but "NGC " cannot be split at all — the
	space-separated case is what --class is for. A shortlist is still returned there, and
	the true total keeps the truncation visible. The depth cap bounds the split even if a
	total ever contradicts its own parts.
	"""
	if total <= SROFFSET_CAP or " " in prefix or depth >= MAX_SPLIT_DEPTH:
		yield prefix
		return
	for char in ALPHABET:
		part = prefix + char
		count = gap_count(part, timeout)
		if count:
			yield from _search_keys(part, count, timeout, depth + 1)


def _collect(key, budget, seen, timeout):
	"""Page one search key, dropping ids an earlier key already produced."""
	out, offset = [], 0
	while len(out) < budget and offset < SROFFSET_CAP:
		ids = parse_search(_search(key, offset, PAGE, timeout))
		if not ids:
			return out
		out += [qid for qid in ids if qid not in seen]
		seen.update(out)
		offset += PAGE
	return out[:budget]


def _class_candidate_ids(p31, prefix, limit, timeout):
	"""Q-ids of gap entries of one Wikidata class, ordered by designation for a stable shortlist."""
	query = CLASS_IDS_QUERY.format(p31=p31, prefix=prefix, limit=int(limit))
	ids = [row["item"]["value"].rsplit("/", 1)[-1] for row in _sparql(query, timeout)]
	return ids, gap_count(prefix, timeout, p31)


def _class_total(p31, prefix, timeout):
	return int(_sparql(CLASS_COUNT_QUERY.format(p31=p31, prefix=prefix), timeout)[0]["n"]["value"])


def _search(prefix, offset, limit, timeout):
	"""One Action API call for the gap query of prefix."""
	response = request("GET", API, timeout=timeout, params={
		"action": "query",
		"list": "search",
		"srsearch": GAP_SEARCH.format(prefix=prefix),
		"srnamespace": 0,
		"srlimit": limit,
		"sroffset": offset,
		"format": "json",
	})
	return response.json()["query"]


def _sparql(query, timeout):
	"""Run a query on WDQS and return its bindings."""
	response = request(
		"POST",
		ENDPOINT,
		timeout=timeout,
		data={"query": query, "format": "json"},
		headers={"Accept": "application/sparql-results+json"},
	)
	return response.json()["results"]["bindings"]


def _detail_payload(ids, timeout):
	"""SPARQL bindings for ids, batched so that no single request grows long."""
	bindings = []
	for start in range(0, len(ids), VALUES_BATCH):
		values = " ".join(f"wd:{qid}" for qid in ids[start:start + VALUES_BATCH])
		bindings += _sparql(DETAIL_QUERY.format(values=values), timeout)
	return {"results": {"bindings": bindings}}


def _row(qid, binding):
	label = binding.get("itemLabel", {}).get("value", "")
	return {"item": qid, "label": "" if label == qid else label, "codes": [], "aliases": []}


def _point(value):
	"""`Point(150.1 2.2)` -> (150.1, 2.2); Wikidata globe coordinates use this form."""
	ra, dec = value.removeprefix("Point(").rstrip(")").split()
	return float(ra), float(dec)
