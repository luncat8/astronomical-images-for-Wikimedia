"""Is the gap real? Wikidata P18 is a proxy, not a verdict (plan §6.2, §6.5 rows 2-3).

Three live behaviours shaped this script (2026-09-26), all of them the same lesson — a catalogue
code is a token, and every free-text search treats it as one:

* `wbsearchentities` is fuzzy: "SH 2-1" returns the Heart Nebula, NGC 281 and Sh 2-129, and ten
  hits later it still has not found the item the coverage audit found. The Q-id comes from the
  audit CSV instead, and a search is only a fallback for a bare designation.
* A quoted Commons full-text search for `"SH 2-1"` returns twenty files, among them a widefield
  rho Ophiuchi shot and an 1890s hymnal, because CirrusSearch strips the punctuation and matches
  `sh 2 1` anywhere. Its hits are printed, never counted.
* The **Commons category sitelink** on the Wikidata item is exact, and its members are the real
  answer. Categories hide files, so the full-text hits are printed beside them rather than
  instead of them.

	experiments/commons_gap.py --file experiments/out/sharpless-gaps.csv "SH 2-252 F"
"""

import csv
import re
import sys
from pathlib import Path

from astroproc.audit.http import request

COMMONS = "https://commons.wikimedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
ENWIKI = "https://en.wikipedia.org/w/api.php"
FILE_NS = 6
CATEGORY_PREFIX = "Category:"
SEARCH_LIMIT = 10
CATEGORY_LIMIT = 50
# P528 is "catalog code", and a code can carry a note: "Sh 2-101 (?)". Anything from "(" on is
# a qualifier, not part of the designation.
NOISE = re.compile(r"[^a-z0-9]")


def code_key(text):
	return NOISE.sub("", text.split("(")[0].casefold())


def get(url, **params):
	return request("GET", url, timeout=30, params={**params, "format": "json"}).json()


def entity(qids):
	"""claims, labels, aliases and sitelinks of each Q-id, keyed by Q-id."""
	data = get(WIKIDATA, action="wbgetentities", ids="|".join(qids),
		props="claims|labels|aliases|sitelinks").get("entities", {})
	return {qid: _item(entity) for qid, entity in data.items() if "missing" not in entity}


def _item(entity):
	"""{item, label, codes, commons_category, article} — the links the gap check needs."""
	codes = [claim["mainsnak"]["datavalue"]["value"]
		for claim in entity.get("claims", {}).get("P528", []) if "datavalue" in claim["mainsnak"]]
	links = entity.get("sitelinks", {})
	return {
		"item": entity["id"],
		"label": entity.get("labels", {}).get("en", {}).get("value", ""),
		"codes": codes,
		"commons_category": links.get("commonswiki", {}).get("title", ""),
		"article": links.get("enwiki", {}).get("title", ""),
	}


def search_item(designation):
	"""Fuzzy fallback: items whose labels or aliases really are this designation."""
	wanted = code_key(designation)
	hits = get(WIKIDATA, action="wbsearchentities", search=designation, language="en",
		type="item", limit=10).get("search", [])
	if not hits:
		return []
	found = entity([hit["id"] for hit in hits])
	return [item for item in found.values()
		if any(code_key(text) == wanted for text in item["codes"] + [item["label"]])]


def category_files(title):
	"""Files inside one Commons category — exact membership, unlike a search."""
	members = get(COMMONS, action="query", list="categorymembers", cmtitle=title,
		cmtype="file", cmlimit=CATEGORY_LIMIT).get("query", {}).get("categorymembers", [])
	return [member["title"] for member in members]


def text_files(name):
	"""Full-text hits, printed as evidence of the search's noise, never as coverage."""
	return [hit["title"] for hit in get(COMMONS, action="query", list="search",
		srsearch=f'"{name}"', srnamespace=FILE_NS, srlimit=SEARCH_LIMIT
	).get("query", {}).get("search", [])]


def lead_image(article):
	"""Lead image of an English article, or "" — an article with none is a G0 candidate."""
	data = get(ENWIKI, action="query", titles=article, prop="pageimages", piprop="original",
		redirects=1)
	return next((page.get("original", {}).get("source", "")
		for page in data.get("query", {}).get("pages", {}).values()), "")


def report(item, designation, searched):
	"""`designation` is the gap code from the audit — the first P528 value would be an LBN
	designation, which is a different name for the same object and reads as a different target."""
	print(f"\n=== {designation}   {item['item']}  {item['label'] or '-'}")
	print(f"  codes: {'; '.join(item['codes']) or '-'}")
	covered = 0
	if item["commons_category"]:
		files = category_files(item["commons_category"])
		covered += len(files)
		print(f"  category {item['commons_category']}: {len(files)} file(s)"
			+ (f"  {files[:3]}" if files else ""))
	else:
		print("  category: none")
	if item["article"]:
		image = lead_image(item["article"])
		covered += 1 if image else 0
		print(f"  article {item['article']}: lead image {image or 'NONE (G0)'}")
	else:
		print("  article: none")
	if searched:
		hits = text_files(designation)
		print(f"  full-text {designation!r}: {len(hits)} hit(s), e.g. {hits[:2]}")
	print(f"  => {covered} item(s) of evidence that it is already illustrated")
	return covered


def from_file(path, only):
	"""Gap rows from `audit sparql --out`, so the Q-ids come from the audit, not a search."""
	with Path(path).open(encoding="utf-8") as handle:
		rows = list(csv.DictReader(handle))
	return [row for row in rows if not only or row["designation"] in only or row["item"] in only]


def main():
	args = sys.argv[1:]
	if args[:1] == ["--file"]:
		rows = from_file(args[1], set(args[2:]))
		items = entity([row["item"] for row in rows])
		for row in rows:
			if row["item"] in items:
				report(items[row["item"]], row["designation"], searched=True)
		return
	for designation in args:
		items = search_item(designation) or entity([])
		if not items:
			print(f"\n=== {designation}: no Wikidata item carries this designation")
			continue
		for item in items:
			report(item, designation, searched=True)


if __name__ == "__main__":
	main()
