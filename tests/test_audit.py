import pytest
import requests

from astroproc.audit import sparql
from astroproc.audit.score import RUBRIC, Score, render_dossier
from astroproc.audit.sparql import DETAIL_QUERY, GAP_SEARCH, parse_response, parse_search


def test_gap_search_uses_index_and_image_filter():
	text = GAP_SEARCH.format(prefix="NGC")
	assert text == "haswbstatement:P528=NGC* -haswbstatement:P18"


def test_detail_query_shape():
	text = DETAIL_QUERY.format(values="wd:Q1 wd:Q2")
	assert "VALUES ?item { wd:Q1 wd:Q2 }" in text
	assert "FILTER NOT EXISTS" not in text, "the image filter is the index query's job"
	assert 'wikibase:language "en,mul"' in text
	assert DETAIL_QUERY.count("{{") == 4, "braces are escaped for str.format"


def test_parse_response_groups_designations_per_item():
	payload = {"results": {"bindings": [
		{
			"item": {"value": "http://www.wikidata.org/entity/Q639464"},
			"itemLabel": {"value": "NGC 6334"},
			"cat": {"value": "RCW 127"},
		},
		{
			"item": {"value": "http://www.wikidata.org/entity/Q639464"},
			"itemLabel": {"value": "NGC 6334"},
			"cat": {"value": "GUM 62"},
			"coords": {"value": "Point(-60.2 -1.4)"},
		},
		{
			"item": {"value": "http://www.wikidata.org/entity/Q3928208"},
			"itemLabel": {"value": "Q3928208"},
			"cat": {"value": "RCW 114"},
		},
	]}}
	rows = parse_response(payload, prefix="RCW ")
	assert [row["item"] for row in rows] == ["Q3928208", "Q639464"], "ordered by designation"
	assert rows[1]["codes"] == ["RCW 127"]
	assert rows[1]["aliases"] == ["GUM 62"]
	assert rows[1]["ra"] == -60.2 and rows[1]["dec"] == -1.4
	assert rows[0]["label"] == "", "a label-less item must not be shown as its own Q-id"


def test_parse_response_prefix_match_is_case_insensitive():
	payload = {"results": {"bindings": [
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "cat": {"value": "SH2-8"}},
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "cat": {"value": "RCW 127"}},
	]}}
	rows = parse_response(payload, prefix="sh2")
	assert rows[0]["codes"] == ["SH2-8"] and rows[0]["aliases"] == ["RCW 127"]


def test_parse_response_keeps_rows_without_coordinates():
	payload = {"results": {"bindings": [
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "cat": {"value": "IC 1284"}},
	]}}
	rows = parse_response(payload, prefix="IC")
	assert "ra" not in rows[0] and "dec" not in rows[0]


def test_parse_search_reads_titles():
	payload = {"searchinfo": {"totalhits": 2}, "search": [{"title": "Q1"}, {"title": "Q2"}]}
	assert parse_search(payload) == ["Q1", "Q2"]


def test_parse_response_keeps_token_prefix_matches():
	"""`Coll*` reaches "Collinder 69" because the token is "Collinder"."""
	payload = {"results": {"bindings": [
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "cat": {"value": "Collinder 69"}},
		{"item": {"value": "http://www.wikidata.org/entity/Q2"}, "cat": {"value": "IC 1284"}},
	]}}
	rows = parse_response(payload, prefix="Coll")
	assert [row["item"] for row in rows] == ["Q1"]
	assert rows[0]["codes"] == ["Collinder 69"]


def test_parse_response_leaves_index_overmatches_visible():
	"""`SH*` also returns Shk objects; the codes are printed so the reader can judge."""
	payload = {"results": {"bindings": [
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "cat": {"value": "SH 2-104"}},
		{"item": {"value": "http://www.wikidata.org/entity/Q2"}, "cat": {"value": "Shk 372"}},
	]}}
	rows = parse_response(payload, prefix="SH")
	assert [row["item"] for row in rows] == ["Q1", "Q2"]


def test_class_anchored_queries():
	count = sparql.CLASS_COUNT_QUERY.format(p31="Q11282", prefix="SH 2-")
	assert "wd:Q11282" in count
	assert 'FILTER(STRSTARTS(?cat, "SH 2-"))' in count
	assert "COUNT(DISTINCT ?item)" in count
	assert "FILTER NOT EXISTS { ?item wdt:P18 ?img }" in count
	ids = sparql.CLASS_IDS_QUERY.format(p31="Q11282", prefix="SH 2-", limit=50)
	assert "ORDER BY ?cat" in ids and "LIMIT 50" in ids


def test_class_candidate_ids_uses_count_and_ordered_ids(monkeypatch):
	def fake_sparql(query, timeout):
		if "COUNT" in query:
			return [{"n": {"value": "273"}}]
		return [{"item": {"value": "http://www.wikidata.org/entity/Q42"}}]

	monkeypatch.setattr(sparql, "_sparql", fake_sparql)
	ids, total = sparql.candidate_ids("SH 2-", limit=5, p31="Q11282")
	assert total == 273 and ids == ["Q42"]


class StubResponse:
	def __init__(self, status_code=200, headers=None):
		self.status_code = status_code
		self.headers = headers or {}

	def json(self):
		return {"ok": True}

	def raise_for_status(self):
		if self.status_code >= 400:
			raise requests.HTTPError(f"{self.status_code}", response=self)


def test_request_retries_a_read_timeout(monkeypatch):
	"""A twelve-call audit lost two calls to a plain read timeout; one retry is the fix."""
	calls = []

	class FlakySession:
		def request(self, method, url, **kwargs):
			calls.append((method, url))
			if len(calls) == 1:
				raise requests.ReadTimeout("slow")
			return StubResponse()

	monkeypatch.setattr(sparql, "_http", FlakySession())
	assert sparql._request("GET", sparql.API, timeout=1).json() == {"ok": True}
	assert len(calls) == 2
	assert calls[0] == calls[1], "the retry repeats the same call"


def test_request_gives_up_after_the_last_attempt(monkeypatch):
	calls = []

	class DeadSession:
		def request(self, method, url, **kwargs):
			calls.append(url)
			raise requests.ReadTimeout("slow")

	monkeypatch.setattr(sparql, "_http", DeadSession())
	with pytest.raises(requests.ReadTimeout):
		sparql._request("GET", sparql.API, timeout=1)
	assert len(calls) == 3


def test_request_waits_out_a_rate_limit(monkeypatch):
	"""A shortlist was killed by an anonymous 429; the API names the wait in Retry-After."""
	slept = []
	responses = [StubResponse(429, {"Retry-After": "2"}), StubResponse()]

	class ThrottledSession:
		def request(self, method, url, **kwargs):
			return responses.pop(0)

	monkeypatch.setattr(sparql, "_http", ThrottledSession())
	monkeypatch.setattr(sparql.time, "sleep", slept.append)
	assert sparql._request("GET", sparql.API, timeout=1).json() == {"ok": True}
	assert slept == [2.0]


def test_request_does_not_retry_a_server_side_timeout(monkeypatch):
	"""504 means the query was too slow; retrying spends the WDQS budget twice for nothing."""
	calls = []

	class SlowQuerySession:
		def request(self, method, url, **kwargs):
			calls.append(url)
			return StubResponse(504)

	monkeypatch.setattr(sparql, "_http", SlowQuerySession())
	with pytest.raises(requests.HTTPError):
		sparql._request("POST", sparql.ENDPOINT, timeout=1)
	assert len(calls) == 1


def test_candidate_ids_stops_at_limit(monkeypatch):
	monkeypatch.setattr(sparql, "_search", lambda prefix, offset, limit, timeout: {
		"searchinfo": {"totalhits": 900},
		"search": [{"title": f"Q{prefix}{offset + i}"} for i in range(limit)],
	})
	ids, total = sparql.candidate_ids("RCW", limit=120)
	assert total == 900 and len(ids) == 120


def test_oversized_prefix_is_split_before_paging(monkeypatch):
	"""list=search cannot page past SROFFSET_CAP, so a huge prefix must be partitioned."""
	totals = {"NGC": 40000, "NGC1": 5, "NGC3": 7}

	def fake_search(prefix, offset, limit, timeout):
		total = totals.get(prefix, 0)
		page = min(limit, total - offset)
		return {
			"searchinfo": {"totalhits": total},
			"search": [{"title": f"{prefix}|{offset + i}"} for i in range(max(page, 0))],
		}

	monkeypatch.setattr(sparql, "_search", fake_search)
	ids, total = sparql.candidate_ids("NGC", limit=50)
	assert total == 40000
	assert ids == [f"NGC1|{i}" for i in range(5)] + [f"NGC3|{i}" for i in range(7)]


def test_multi_token_prefix_is_not_partitioned(monkeypatch):
	"""A wildcard binds to the last token only, so a space-containing prefix cannot split."""
	def fake_search(prefix, offset, limit, timeout):
		return {"searchinfo": {"totalhits": 33478}, "search": []}

	monkeypatch.setattr(sparql, "_search", fake_search)
	ids, total = sparql.candidate_ids("NGC ", limit=50)
	assert (ids, total) == ([], 33478)


def test_rubric_hard_gates_drop():
	score = Score()
	for row in range(1, 11):
		score.set(row, 3)
	score.set(1, 0)
	assert "drop" in score.verdict()


def test_rubric_scoring():
	score = Score()
	for row, *_ in RUBRIC:
		score.set(row, 2)
	assert score.total() == 20
	assert score.verdict() == "pursue"
	assert "10" in score.render() and "total 20/30" in score.render()


def test_rubric_rejects_out_of_range():
	score = Score()
	with pytest.raises(ValueError):
		score.set(1, 5)
	with pytest.raises(KeyError):
		score.set(11, 1)
	with pytest.raises(ValueError):
		score.total()


def test_dossier_renders_todo_for_missing_fields():
	text = render_dossier(designation="Sh2-1", common_name="?", score="25/30", verdict="pursue")
	assert "Sh2-1" in text
	assert text.count("<TODO>") >= 10
	assert "Data licence:" in text
