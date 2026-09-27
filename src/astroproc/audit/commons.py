"""Is the gap real? Wikidata P18 is a proxy, and a catalogue code is a token (plan §6.2, §6.5).

`check` gathers the evidence for a batch of items; `candidates` is the step the chain runs, and it
is where the evidence becomes a verdict: it takes the gap shortlist together with what the archive
audit found, and keeps only the rows that are still candidates. The filter is the point — each row
costs a category listing and an article lookup, so checking 274 Sharpless gaps one by one spends 548
requests on a question `audit pointed` has already answered for 6.

Three live behaviours shaped this module (measured 2026-09-26), all of them the same lesson:

* `wbsearchentities` is fuzzy — "SH 2-1" returns the Heart Nebula, NGC 281 and Sh 2-129 — so the
  Q-id comes from the audit CSV and a search is only a fallback for a bare designation.
* A quoted Commons full-text search for `"SH 2-1"` returns twenty files, among them a widefield
  rho Ophiuchi shot and an 1890s hymnal, because CirrusSearch strips punctuation and matches
  `sh 2 1` anywhere. Hits are returned as evidence to read, never as a count.
* The **Commons category sitelink** on the item is exact, and its members are the real answer.
  Categories also hide files, so both signals are returned and the caller decides.
"""

import csv
import re
from pathlib import Path

from .coords import split_codes
from .http import request

COMMONS = "https://commons.wikimedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
ENWIKI = "https://en.wikipedia.org/w/api.php"
FILE_NS = 6
SEARCH_LIMIT = 10
CATEGORY_LIMIT = 50
# `wbgetentities` caps `ids` at 50 per request, and the shortlist is 274 rows: one request for all
# of them answers with the first 50 and no error, which would read as "most gaps are covered".
ENTITY_BATCH = 50
# P528 is "catalog code", and a code can carry a note: "Sh 2-101 (?)". Anything from "(" on is a
# qualifier, not part of the designation.
NOISE = re.compile(r"[^a-z0-9]")

# The row 2 verdicts a machine can reach. G1-G4 need the files read — is the survey cutout
# grayscale, is the colour version clipped — which no API answers; what the APIs do answer is the
# two ends. A gap that `audit pointed`/`audit sets` called an answer is the only kind worth asking
# about, so those verdicts are listed here beside them.
COVERED = "covered"
G0_ARTICLE = "G0 (article without a lead image)"
G0_NO_ARTICLE = "G0 (no article, notability unproven)"
ANSWER_VERDICTS = ("imaged", "colour_set")
# The columns `write_candidates` writes, in reading order: what the audit found (designation, item,
# aliases), the Commons evidence, the gap class, then the archive row the candidate came from.
CANDIDATE_COLUMNS = (
	"designation", "item", "label", "aliases", "otype", "gap", "category", "n_category_files",
	"category_files", "article", "lead_image", "count", "text_hits", "ra", "dec", "archive_name",
	"verdict", "obs_id", "instrument", "filters", "fov_arcsec", "public", "rights",
)


def code_key(text):
	return NOISE.sub("", text.split("(")[0].casefold())


def get(url, **params):
	return request("GET", url, timeout=30, params={**params, "format": "json"}).json()


def entity(qids):
	"""claims, labels and sitelinks of each Q-id, keyed by Q-id, in batches the API accepts."""
	found = {}
	for start in range(0, len(qids), ENTITY_BATCH):
		data = get(WIKIDATA, action="wbgetentities", ids="|".join(qids[start:start + ENTITY_BATCH]),
			props="claims|labels|aliases|sitelinks").get("entities", {})
		found.update({qid: _item(entry) for qid, entry in data.items() if "missing" not in entry})
	return found


def _item(entry):
	"""{item, label, codes, category, article} — the links the gap check needs."""
	codes = [claim["mainsnak"]["datavalue"]["value"]
		for claim in entry.get("claims", {}).get("P528", []) if "datavalue" in claim["mainsnak"]]
	links = entry.get("sitelinks", {})
	return {
		"item": entry["id"],
		"label": entry.get("labels", {}).get("en", {}).get("value", ""),
		"codes": codes,
		"category": links.get("commonswiki", {}).get("title", ""),
		"article": links.get("enwiki", {}).get("title", ""),
	}


def search_item(designation):
	"""Fuzzy fallback: items whose P528 codes or label really are this designation."""
	wanted = code_key(designation)
	hits = get(WIKIDATA, action="wbsearchentities", search=designation, language="en",
		type="item", limit=SEARCH_LIMIT).get("search", [])
	found = entity([hit["id"] for hit in hits])
	return [item for item in found.values()
		if any(code_key(text) == wanted for text in item["codes"] + [item["label"]])]


def category_files(title):
	"""Files inside one Commons category — exact membership, unlike a search."""
	members = get(COMMONS, action="query", list="categorymembers", cmtitle=title,
		cmtype="file", cmlimit=CATEGORY_LIMIT).get("query", {}).get("categorymembers", [])
	return [member["title"] for member in members]


def text_files(name):
	"""Full-text hits — the search's own noise, kept because hiding a hit is worse than showing one."""
	return [hit["title"] for hit in get(COMMONS, action="query", list="search",
		srsearch=f'"{name}"', srnamespace=FILE_NS, srlimit=SEARCH_LIMIT
	).get("query", {}).get("search", [])]


def lead_image(article):
	"""Lead image of an English article, or "" — an article with none is a G0 candidate."""
	data = get(ENWIKI, action="query", titles=article, prop="pageimages", piprop="original", redirects=1)
	return next((page.get("original", {}).get("source", "")
		for page in data.get("query", {}).get("pages", {}).values()), "")


def evidence(item, designation, searched=False):
	"""Everything known about whether `item` is already illustrated.

	`designation` is the gap code from the audit: the item's first P528 value can be an LBN
	designation, a different name for the same object, and it reads as a different target.
	"""
	files = category_files(item["category"]) if item["category"] else []
	image = lead_image(item["article"]) if item["article"] else ""
	return {
		**item,
		"designation": designation,
		"category_files": files,
		"lead_image": image,
		"text_hits": text_files(designation) if searched else [],
		# the two exact signals: files in the Commons category, and an article that illustrates
		# the object. A full-text hit is neither, because CirrusSearch cannot tell "SH 2-1" from
		# "sh 2 1" inside a hymnal title.
		"illustrated": bool(files or image),
		"count": len(files) + bool(image),
	}


def check(qids, searched=False):
	"""`evidence` for a batch of Q-ids, in the order the audit listed them."""
	items = entity(list(qids))
	return [evidence(items[qid], qid, searched=searched) for qid in qids if qid in items]


def classify(row):
	"""§6.5 row 2, as far as three APIs can decide it — the hard gate, in both directions.

	`covered` means the P18 proxy was wrong and the candidate is dropped, which is the `SH 2-20`
	case: no image on the item, illustrated on Commons as `RCW 141`. Nothing at all means G0, the
	class the archive audit exists to find. An article with no lead image is G0 too and is the
	strongest form of it — the article is evidence the object is notable (row 3), and the missing
	image is the gap. No article *and* no category leaves row 3 open, which is why the two G0
	readings are kept apart rather than averaged into one score.
	"""
	if row["category_files"] or row["lead_image"]:
		return COVERED
	return G0_ARTICLE if row["article"] else G0_NO_ARTICLE


def candidates(gaps, targets=None, searched=False, answered_only=True):
	"""Gap rows reduced to the ones still worth checking, each with its evidence and gap class.

	`gaps` is a path to (or the rows of) the CSV `audit sparql --out` writes. `targets`, when given,
	is a path to (or the rows of) `audit pointed` / `audit sets` output: the shortlist. With
	`answered_only` — the default, and what makes the chain a pipeline — only the designations those
	rows answered for are checked, because a 261-row audit dump is 522 requests for a question
	already decided. `answered_only=False` checks every row of the shortlist, which is what a curated
	list wants: the HST pointings that missed `Sh 2-1` still leave it a real G0 candidate for a
	ground-based archive, and a row that says "footprint missed" cannot decide that for you. A
	hand-made target list without a `verdict` column is taken as given either way.

	Matching is on any designation or cross-identification of the gap row, because the archive audit
	names a target with whichever code it resolved and `SH 2-20` is `RCW 141` (§6.3.1). The archive
	row is joined back onto the result, so the score and the dossier get the footprint and the licence
	without a second lookup.
	"""
	gap_rows = _records(gaps)
	target_rows = None if targets is None else _records(targets)
	wanted = None if target_rows is None else _wanted_targets(target_rows, answered_only)
	archive = {} if target_rows is None else {row["target"].strip().casefold(): row for row in target_rows}
	selected = [row for row in gap_rows if wanted is None or _matches(row, wanted)]
	items = entity([row["item"] for row in selected if row.get("item")])
	out = []
	for row in selected:
		item = items.get(row.get("item"))
		if item is None:
			continue
		designation = (split_codes(row.get("designation", "")) or [row["item"]])[0]
		found = evidence(item, designation, searched=searched)
		found["gap"] = classify(found)
		# the count is part of the row, not of the CSV writer: the terminal output and the file both
		# read it, and a key that only exists after writing is a key the next reader does not have
		found["n_category_files"] = len(found["category_files"])
		found["aliases"] = split_codes(row.get("aliases", ""))
		found.update({key: row.get(key, "") for key in ("ra", "dec")})
		# joined on the same rule that selected the row — any code or cross-identification — because
		# the archive audit names a target with whichever designation it resolved, not the one the
		# gap was found under
		found.update({key: value for key, value
			in _archive_row(archive, designation, found["aliases"]).items()
			if key in CANDIDATE_COLUMNS})
		out.append(found)
	return out


def write_candidates(rows, path):
	"""The candidates as CSV — the file `audit score` reads, one row per judged candidate."""
	records = [{**row,
		"category_files": ";".join(row["category_files"]),
		"text_hits": ";".join(row["text_hits"]),
		"aliases": ";".join(row["aliases"]),
	} for row in rows]
	with Path(path).open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=list(CANDIDATE_COLUMNS), extrasaction="ignore")
		writer.writeheader()
		writer.writerows(records)
	return path


def _wanted_targets(rows, answered_only):
	"""The target names to check, casefolded. A missing verdict column is a hand-made list: every
	row is a request the operator made deliberately."""
	names = {row["target"].strip().casefold() for row in rows
		if not answered_only or "verdict" not in row or row.get("verdict") in ANSWER_VERDICTS}
	return names - {""}


def _archive_row(archive, designation, aliases):
	"""The archive row for the gap: the first designation of the row that the audit answered for."""
	for code in [designation, *aliases]:
		if code.strip().casefold() in archive:
			return archive[code.strip().casefold()]
	return {}


def _matches(gap_row, wanted):
	"""Is any designation or cross-identification of this gap row in the target list?"""
	text = f"{gap_row.get('designation', '')};{gap_row.get('aliases', '')}"
	return any(code.casefold() in wanted for code in split_codes(text))


def _records(rows):
	"""(rows) from a list of dicts, or the rows of a CSV path."""
	if isinstance(rows, (str, Path)):
		with Path(rows).open(encoding="utf-8") as handle:
			return list(csv.DictReader(handle))
	return list(rows)
