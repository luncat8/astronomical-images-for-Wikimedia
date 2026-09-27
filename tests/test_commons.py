"""The gap check P18 cannot do (plan §6.2, §6.3.1), with the three APIs stubbed.

`SH 2-20` is the case these tests exist for: the Wikidata item has no P18 image, so the audit calls
it a gap, and it is in fact illustrated on Commons under the cross-identification `RCW 141`. The
tests pin the two rules that catch it — the archive's category decides, a text search does not.
"""

from astroproc.audit import commons


def stub(monkeypatch, wikidata=None, files=None, enwiki=None):
	"""Answer the three APIs from dictionaries keyed by the argument that distinguishes them."""
	responses = {
		"wbgetentities": wikidata or {"entities": {}},
		"wbsearchentities": {"search": []},
	}
	listed = files or {}

	def fake_get(url, **params):
		if url == commons.WIKIDATA:
			return responses[params["action"]]
		if url == commons.ENWIKI:
			return enwiki or {"query": {"pages": {}}}
		return listed.get(params.get("list"), {"query": {}})

	monkeypatch.setattr(commons, "get", fake_get)


def item(qid="Q88634040", codes=("SH 2-252 F",), category="", article="", label=""):
	entity = {"id": qid, "claims": {"P528": [{"mainsnak": {"datavalue": {"value": code}}} for code in codes]},
		"sitelinks": {}}
	if category:
		entity["sitelinks"]["commonswiki"] = {"title": category}
	if article:
		entity["sitelinks"]["enwiki"] = {"title": article}
	if label:
		entity["labels"] = {"en": {"value": label}}
	return entity


def test_code_key_strips_punctuation_and_qualifiers():
	assert commons.code_key("SH 2-252 F") == "sh2252f"
	assert commons.code_key("Sh 2-101 (?)") == "sh2101", "a qualifier is not part of the designation"
	assert commons.code_key("RCW 141") == "rcw141"


def test_entity_reads_codes_and_sitelinks(monkeypatch):
	stub(monkeypatch, wikidata={"entities": {
		"Q88634040": item(category="Category:NGC 2174", article="NGC 2174", label="NGC 2174"),
		"Q1": {"id": "Q1", "missing": ""},
	}})
	found = commons.entity(["Q88634040", "Q1"])
	assert list(found) == ["Q88634040"], "a missing entity is not a gap"
	assert found["Q88634040"]["codes"] == ["SH 2-252 F"]
	assert found["Q88634040"]["category"] == "Category:NGC 2174"
	assert found["Q88634040"]["article"] == "NGC 2174"


def test_evidence_counts_the_category_and_the_lead_image(monkeypatch):
	stub(monkeypatch,
		wikidata={"entities": {"Q1": item(category="Category:RCW 141", article="RCW 141")}},
		files={
			"categorymembers": {"query": {"categorymembers": [{"title": "File:RCW 141.jpg"},
				{"title": "File:RCW 141 (cropped).jpg"}]}},
			"search": {"query": {"search": [{"title": "File:An unrelated widefield shot.jpg"}]}},
		},
		enwiki={"query": {"pages": {"1": {"original": {"source": "File:RCW141.jpg"}}}}})
	row = commons.check(["Q1"])[0]
	assert row["category"] == "Category:RCW 141" and row["category_files"] == [
		"File:RCW 141.jpg", "File:RCW 141 (cropped).jpg"]
	assert row["lead_image"] == "File:RCW141.jpg"
	assert row["count"] == 3, "two files in the category and one lead image"
	assert row["illustrated"] is True
	assert row["text_hits"] == [], "a full-text search is noise until something says otherwise"


def test_article_without_a_lead_image_is_evidence_but_not_coverage(monkeypatch):
	"""`Sh 2-1` and `Sh 2-7` have articles and no lead image: the purest form of G0, invisible to P18."""
	stub(monkeypatch,
		wikidata={"entities": {"Q1": item(article="Sh 2-1")}},
		enwiki={"query": {"pages": {"1": {}}}})
	row = commons.check(["Q1"])[0]
	assert row["lead_image"] == "" and row["category"] == ""
	assert row["illustrated"] is False and row["count"] == 0
	assert row["article"] == "Sh 2-1", "the article itself is a fact about the object worth keeping"


def test_evidence_uses_the_gap_code_not_the_first_p528_value(monkeypatch):
	"""The item's first P528 value can be an LBN designation — the same object under another name,
	which reads as a different target if the search uses it."""
	stub(monkeypatch,
		wikidata={"entities": {"Q1": item(codes=("LBN 1234-19", "SH 2-101"))}},
		files={"search": {"query": {"search": [{"title": "File:Hymnal, page 2.jpg"}]}}})
	row = commons.evidence(commons.entity(["Q1"])["Q1"], "SH 2-101", searched=True)
	assert row["designation"] == "SH 2-101"
	assert row["codes"] == ["LBN 1234-19", "SH 2-101"]
	assert row["text_hits"] == ["File:Hymnal, page 2.jpg"]
	assert row["illustrated"] is False, "a hymnal page titled `sh 2 101` is not an illustration"


def test_search_item_only_accepts_a_real_match(monkeypatch):
	stub(monkeypatch,
		wikidata={"entities": {
			"Q1": item(qid="Q1", codes=("SH 2-1",)), "Q2": item(qid="Q2", codes=("SH 2-129",))}})

	def fake_get(url, **params):
		if params["action"] == "wbsearchentities":
			return {"search": [{"id": "Q1"}, {"id": "Q2"}]}
		return {"entities": {"Q1": item(qid="Q1", codes=("SH 2-1",)), "Q2": item(qid="Q2", codes=("SH 2-129",))}}

	monkeypatch.setattr(commons, "get", fake_get)
	found = commons.search_item("SH 2-1")
	assert [row["item"] for row in found] == ["Q1"], "fuzzy search hits that are not this object are dropped"


def test_check_keeps_audit_order_and_skips_missing_items(monkeypatch):
	stub(monkeypatch, wikidata={"entities": {"Q2": item(qid="Q2", codes=("SH 2-4",))}})
	rows = commons.check(["Q1", "Q2", "Q3"])
	assert [row["item"] for row in rows] == ["Q2"], "an item Wikidata does not have is not a gap"
