import pytest

from astroproc.audit import coords, http
from astroproc.audit.coords import parse_sesame, resolve_names, write_targets

SESAME_OK = """<?xml version="1.0" encoding="UTF-8" ?>
<Sesame>
<Target option="SNV">
  <name>Sh2-104</name>
  <Resolver name="Sc=Simbad (CDS, via client/server)">
    <oid>2932760</oid>
    <otype>HII</otype>
    <jradeg>304.46875</jradeg>
    <jdedeg>36.82333333</jdedeg>
    <oname>SH  2-104</oname>
  </Resolver>
</Target>
</Sesame>"""

SESAME_MISS = """<?xml version="1.0" encoding="UTF-8" ?>
<Sesame>
<Target option="SNV">
  <name>Abell 9999</name>
  <INFO> *** NNNothing found *** </INFO>
</Target>
</Sesame>"""


def test_parse_sesame_reads_the_position_and_its_provenance():
	row = parse_sesame(SESAME_OK)["Sh2-104"]
	assert (row["ra"], row["dec"]) == (304.46875, 36.82333333)
	assert row["otype"] == "HII" and row["object"] == "SH  2-104"
	assert row["source"].startswith("Sc=Simbad")


def test_parse_sesame_keeps_a_negative_result():
	"""Nothing found is an answer: the target stays, with an empty position."""
	row = parse_sesame(SESAME_MISS)["Abell 9999"]
	assert row["ra"] is None and row["dec"] is None and row["source"] == ""


def test_parse_sesame_takes_the_first_resolver_with_a_position():
	"""Sesame consults the next database only when the previous one does not know the name."""
	text = """<?xml version="1.0" encoding="UTF-8" ?>
<Sesame>
<Target option="SNV">
  <name>UGC 12557</name>
  <Resolver name="Sc=Simbad"><INFO>from cache</INFO></Resolver>
  <Resolver name="N=Ned"><jradeg>350.619</jradeg><jdedeg>29.181</jdedeg><oname>Z 497-8</oname></Resolver>
</Target>
</Sesame>"""
	row = parse_sesame(text)["UGC 12557"]
	assert (row["ra"], row["dec"], row["source"]) == (350.619, 29.181, "N=Ned")


def test_resolve_names_preserves_order_and_reports_misses(monkeypatch):
	monkeypatch.setattr(coords, "_query", lambda names, timeout: SESAME_OK if "Sh2-104" in names else SESAME_MISS)
	rows = resolve_names(["Sh2-104", "Abell 9999"])
	assert [row["name"] for row in rows] == ["Sh2-104", "Abell 9999"]
	assert rows[0]["ra"] == 304.46875 and rows[0]["via"] == "Sh2-104"
	assert rows[1]["ra"] is None and rows[1]["via"] == "", "an unresolved row has no via"


def test_resolve_names_batches_the_request(monkeypatch):
	batches = []

	def fake_query(names, timeout):
		batches.append(list(names))
		return SESAME_OK

	monkeypatch.setattr(coords, "_query", fake_query)
	resolve_names([f"Sh2-{i}" for i in range(5)], batch=2)
	assert [len(chunk) for chunk in batches] == [2, 2, 1]


def test_resolve_names_matches_a_padded_echo(monkeypatch):
	"""Sesame echoes the name it was given; whitespace must not lose the row."""
	monkeypatch.setattr(coords, "_query", lambda names, timeout: SESAME_OK.replace("<name>Sh2-104", "<name> Sh2-104 "))
	assert resolve_names(["Sh2-104"])[0]["ra"] == 304.46875


def test_query_uses_the_bare_batch_form(monkeypatch):
	"""`Name=x` and `x=` both resolve to nothing, silently, so the query string is hand-built."""
	seen = {}

	def fake_request(method, url, timeout, **kwargs):
		seen["url"] = url
		raise RuntimeError("no network in tests")

	monkeypatch.setattr(coords, "request", fake_request)
	with pytest.raises(RuntimeError):
		coords._query(["Sh2-104", "RCW 5"], timeout=1)
	assert seen["url"].endswith("?Sh2-104&RCW%205")


def test_alias_retry_fills_a_row_the_own_designation_missed(monkeypatch):
	"""§6.2 cross-identification: a gap under one code is often covered under another."""
	answers = {"Sh2-999": SESAME_MISS, "RCW 158": SESAME_OK.replace("Sh2-104", "RCW 158")}
	monkeypatch.setattr(coords, "_query", lambda names, timeout: "".join(
		answers[name] for name in names if name in answers))
	row = {"codes": ["Sh2-999"], "aliases": ["RCW 158", "GUM 111"], "name": "Sh2-999"}
	out = coords._attach_coordinates([row], timeout=1)
	assert out[0]["ra"] == 304.46875
	assert out[0]["via"] == "RCW 158" and out[0]["name"] == "Sh2-999"


def test_alias_retry_stops_at_the_first_hit(monkeypatch):
	"""A second alias must not overwrite the first that answered."""
	asked = []
	monkeypatch.setattr(coords, "_query", lambda names, timeout: asked.extend(names) or SESAME_MISS)
	row = {"codes": ["Sh2-999"], "aliases": ["RCW 158", "GUM 111"]}
	coords._attach_coordinates([row], timeout=1)
	assert asked == ["Sh2-999", "RCW 158", "GUM 111"]


def test_alias_retry_is_bounded_and_skippable(monkeypatch):
	asked = []
	monkeypatch.setattr(coords, "_query", lambda names, timeout: asked.extend(names) or SESAME_MISS)
	row = {"codes": ["Sh2-999"], "aliases": [f"A{i}" for i in range(10)]}
	coords._attach_coordinates([row], timeout=1)
	assert asked[1:] == [f"A{i}" for i in range(coords.MAX_ALIASES)]

	asked.clear()
	monkeypatch.setattr(coords, "_query", lambda names, timeout: asked.extend(names) or SESAME_MISS)
	coords._attach_coordinates([{"codes": ["Sh2-999"], "aliases": ["RCW 158"]}], timeout=1, use_aliases=False)
	assert asked == ["Sh2-999"]


def test_write_targets_keeps_mast_columns_first_and_drops_internals(tmp_path):
	path = tmp_path / "targets.csv"
	write_targets([
		{"name": "Sh2-104", "ra": 304.46875, "dec": 36.823, "source": "Sc=Simbad",
		 "object": "SH  2-104", "otype": "HII", "via": "Sh2-104", "aliases": ["RCW 158"]},
		{"name": "Abell 9999", "ra": None, "dec": None, "source": "", "object": "",
		 "otype": "", "via": "", "aliases": []},
	], path)
	lines = path.read_text().strip().splitlines()
	assert lines[0] == "name,ra,dec,source,object,otype,via"
	assert lines[1].startswith("Sh2-104,304.46875,36.823")
	assert lines[2].startswith("Abell 9999,,"), "an unresolved target is kept, with empty coordinates"
	assert "RCW 158" not in lines[1]


def test_read_designations_keeps_aliases_and_rejects_unknown_columns(tmp_path):
	path = tmp_path / "shortlist.csv"
	path.write_text("designation\nSH 2-104; RCW 158\nRCW 5\n\n")
	rows = coords._read_designations(path)
	assert rows == [{"name": "SH 2-104", "aliases": ["RCW 158"]}, {"name": "RCW 5", "aliases": []}]

	bad = tmp_path / "bad.csv"
	bad.write_text("object\nM31\n")
	with pytest.raises(SystemExit):
		coords._read_designations(bad)


def test_mast_cross_check_skips_targets_without_coordinates(tmp_path, monkeypatch):
	"""An unresolved designation must not read as "no data": the skip is counted and visible."""
	from astropy.table import Table
	from astroquery.mast import Observations
	from astroproc.audit import mast

	path = tmp_path / "targets.csv"
	path.write_text("name,ra,dec\nSh2-104,304.46875,36.823\nAbell 9999,,\n")
	monkeypatch.setattr(Observations, "query_criteria", lambda **kwargs: Table())
	table = mast.coverage(path)
	assert [row["target"] for row in table] == ["Sh2-104"]
	assert table.meta["skipped_without_coords"] == 1
	assert table.meta["radius_deg"] == 0.01


def test_http_retries_a_read_timeout(monkeypatch):
	"""A twelve-call audit lost two calls to a plain read timeout; one retry is the fix."""
	calls = []

	class FlakySession:
		def request(self, method, url, **kwargs):
			calls.append((method, url))
			if len(calls) == 1:
				raise http.requests.ReadTimeout("slow")
			return StubResponse()

	assert http.request("GET", "https://example.invalid", timeout=1, session=FlakySession()).json() == {"ok": True}
	assert calls[0] == calls[1], "the retry repeats the same call"


def test_http_gives_up_after_the_last_attempt():
	class DeadSession:
		def request(self, method, url, **kwargs):
			raise http.requests.ReadTimeout("slow")

	with pytest.raises(http.requests.ReadTimeout):
		http.request("GET", "https://example.invalid", timeout=1, session=DeadSession())


def test_http_waits_out_a_rate_limit(monkeypatch):
	"""A shortlist was killed by an anonymous 429; the API names the wait in Retry-After."""
	slept = []
	responses = [StubResponse(429, {"Retry-After": "2"}), StubResponse()]

	class ThrottledSession:
		def request(self, method, url, **kwargs):
			return responses.pop(0)

	monkeypatch.setattr(http.time, "sleep", slept.append)
	http.request("GET", "https://example.invalid", timeout=1, session=ThrottledSession())
	assert slept == [2.0]


def test_http_does_not_retry_a_server_side_timeout():
	"""504 means the query was too slow; retrying spends the budget twice for nothing."""
	calls = []

	class SlowQuerySession:
		def request(self, method, url, **kwargs):
			calls.append(url)
			return StubResponse(504)

	with pytest.raises(http.requests.HTTPError):
		http.request("GET", "https://example.invalid", timeout=1, session=SlowQuerySession())
	assert len(calls) == 1


class StubResponse:
	def __init__(self, status_code=200, headers=None):
		self.status_code = status_code
		self.headers = headers or {}

	def json(self):
		return {"ok": True}

	def raise_for_status(self):
		if self.status_code >= 400:
			raise http.requests.HTTPError(f"{self.status_code}", response=self)


def test_anchored_shortlist_shows_a_matched_item_under_its_matching_code():
	"""The anchored path filters server-side with STRSTARTS, so the client guard must be exact.

	An item holding both "SH 1-5" and "SH 2-4" is a "SH 2-" gap through the second code. The
	looser token rule every code of both catalogues shares would list it as "SH 1-5", which
	is a different object and a wrong name to resolve and to report.
	"""
	from astroproc.audit.sparql import parse_response

	payload = {"results": {"bindings": [
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "cat": {"value": "SH 1-5"}},
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "cat": {"value": "SH 2-4"}},
	]}}
	rows = parse_response(payload, prefix="SH 2-", anchored=True)
	assert len(rows) == 1
	assert rows[0]["codes"] == ["SH 2-4"] and rows[0]["aliases"] == ["SH 1-5"]


def test_index_shortlist_keeps_token_prefix_semantics():
	"""`Coll*` reaches "Collinder 69" because the token is "Collinder" — unchanged by the split."""
	from astroproc.audit.sparql import parse_response

	payload = {"results": {"bindings": [
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "cat": {"value": "Collinder 69"}},
		{"item": {"value": "http://www.wikidata.org/entity/Q2"}, "cat": {"value": "Collezione Ansaldi B 905"}},
	]}}
	rows = parse_response(payload, prefix="Coll")
	assert sorted(row["codes"][0] for row in rows) == ["Collezione Ansaldi B 905", "Collinder 69"]


def test_mast_coverage_tolerates_masked_instrument_columns(tmp_path, monkeypatch):
	"""MAST masks the instrument where it is unknown, and a masked value is not hashable."""
	from astropy.table import MaskedColumn, Table
	from astroquery.mast import Observations
	from astroproc.audit.mast import coverage

	observations = Table({
		"instrument_name": MaskedColumn(["TESS", "", "HST/WFC3"], mask=[False, True, False]),
		"filters": MaskedColumn(["g,i,r", "CLEAR", ""], mask=[False, False, True]),
	})
	monkeypatch.setattr(Observations, "query_criteria", lambda **kwargs: observations)
	path = tmp_path / "targets.csv"
	path.write_text("name,ra,dec\nSh2-104,304.46875,36.823\n")
	row = coverage(path)[0]
	assert row["instruments"] == "HST/WFC3,TESS"
	assert row["filters"] == "g,i,r"


def test_gap_csv_round_trips_into_the_resolver(tmp_path):
	"""`audit sparql --out` -> `audit coords --csv` must not lose the cross-identification set."""
	from astroproc.audit.sparql import parse_response, write_gaps

	payload = {"results": {"bindings": [
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "itemLabel": {"value": "SH 2-4"},
		 "cat": {"value": "SH 2-4"}, "coords": {"value": "Point(259.6 -39.3)"}},
		{"item": {"value": "http://www.wikidata.org/entity/Q1"}, "cat": {"value": "SH 1-5"}},
	]}}
	path = tmp_path / "gaps.csv"
	write_gaps(parse_response(payload, prefix="SH 2-", anchored=True), path)
	assert path.read_text().splitlines()[0] == "designation,aliases,item,label,ra,dec"
	rows = coords._read_designations(path)
	assert rows == [{"name": "SH 2-4", "aliases": ["SH 1-5"]}]
