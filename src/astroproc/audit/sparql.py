"""Wikidata SPARQL batch audit (plan §6.2, entry point 0.B).

Finds catalogue entries with no P18 image. A gap found under one designation may be
covered under another — cross-identify with SIMBAD/NED before concluding anything.
"""

import requests

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "astroproc/0.1 (Wikimedia astronomy coverage audit; plan.md §6.2)"

QUERY = """
SELECT ?item ?itemLabel ?cat ?coords WHERE {{
  ?item wdt:P528 ?cat .
  FILTER(STRSTARTS(?cat, "{prefix}"))
  FILTER NOT EXISTS {{ ?item wdt:P18 ?img }}
  OPTIONAL {{ ?item wdt:P625 ?coords . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT {limit}
"""


def missing_p18(prefix, limit=200, timeout=60):
	"""Rows of {item, label, cat, ra, dec} for catalogue objects without a P18 image."""
	response = requests.post(
		ENDPOINT,
		data={"query": QUERY.format(prefix=prefix, limit=int(limit)), "format": "json"},
		headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
		timeout=timeout,
	)
	response.raise_for_status()
	return parse_response(response.json())


def parse_response(payload):
	rows = []
	for binding in payload["results"]["bindings"]:
		row = {
			"item": binding["item"]["value"],
			"label": binding.get("itemLabel", {}).get("value", ""),
			"cat": binding.get("cat", {}).get("value", ""),
		}
		if "coords" in binding:
			ra, dec = binding["coords"]["value"].removeprefix("Point(").rstrip(")").split()
			row["ra"], row["dec"] = float(ra), float(dec)
		rows.append(row)
	return rows
