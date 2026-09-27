"""Is the gap real? Wikidata P18 is a proxy, and a catalogue code is a token (plan §6.2, §6.5).

Three live behaviours shaped this module (measured 2026-09-26), all of them the same lesson:

* `wbsearchentities` is fuzzy — "SH 2-1" returns the Heart Nebula, NGC 281 and Sh 2-129 — so the
  Q-id comes from the audit CSV and a search is only a fallback for a bare designation.
* A quoted Commons full-text search for `"SH 2-1"` returns twenty files, among them a widefield
  rho Ophiuchi shot and an 1890s hymnal, because CirrusSearch strips punctuation and matches
  `sh 2 1` anywhere. Hits are returned as evidence to read, never as a count.
* The **Commons category sitelink** on the item is exact, and its members are the real answer.
  Categories also hide files, so both signals are returned and the caller decides.
"""

import re

from .http import request

COMMONS = "https://commons.wikimedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
ENWIKI = "https://en.wikipedia.org/w/api.php"
FILE_NS = 6
SEARCH_LIMIT = 10
CATEGORY_LIMIT = 50
# P528 is "catalog code", and a code can carry a note: "Sh 2-101 (?)". Anything from "(" on is a
# qualifier, not part of the designation.
NOISE = re.compile(r"[^a-z0-9]")


def code_key(text):
	return NOISE.sub("", text.split("(")[0].casefold())


def get(url, **params):
	return request("GET", url, timeout=30, params={**params, "format": "json"}).json()


def entity(qids):
	"""claims, labels and sitelinks of each Q-id, keyed by Q-id."""
	data = get(WIKIDATA, action="wbgetentities", ids="|".join(qids),
		props="claims|labels|aliases|sitelinks").get("entities", {})
	return {qid: _item(entry) for qid, entry in data.items() if "missing" not in entry}


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
