"""The gap check P18 cannot do (plan §6.2, §6.3.1, §6.5 row 2), with the three APIs stubbed.

`SH 2-20` is the case these tests exist for: the Wikidata item has no P18 image, so the audit calls
it a gap, and it is in fact illustrated on Commons under the cross-identification `RCW 141`. The
tests pin the two rules that catch it — the archive's category decides, a text search does not.
"""

import csv

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


def gap_csv(tmp_path, rows):
	path = tmp_path / "gaps.csv"
	path.write_text("designation,aliases,item,label,ra,dec\n" + "\n".join(rows) + "\n")
	return path


def test_classify_separates_the_two_g0_readings():
	"""An article with no lead image is G0 with row 3 answered; no article leaves row 3 open."""
	assert commons.classify({"category_files": ["File:X.jpg"], "lead_image": "", "article": "X"}) == commons.COVERED
	assert commons.classify({"category_files": [], "lead_image": "File:L.jpg", "article": "X"}) == commons.COVERED
	assert commons.classify({"category_files": [], "lead_image": "", "article": "Sh 2-1"}) == commons.G0_ARTICLE
	assert commons.classify({"category_files": [], "lead_image": "", "article": ""}) == commons.G0_NO_ARTICLE


def test_entity_batches_the_ids_the_api_accepts(monkeypatch):
	"""274 gap rows in one `wbgetentities` call answers with the first 50 and no error."""
	calls = []

	def fake_get(url, **params):
		calls.append(params["ids"].split("|"))
		return {"entities": {qid: item(qid=qid) for qid in params["ids"].split("|")}}

	monkeypatch.setattr(commons, "get", fake_get)
	qids = [f"Q{index}" for index in range(120)]
	found = commons.entity(qids)
	assert list(found) == qids, "order and completeness survive the batching"
	assert [len(call) for call in calls] == [50, 50, 20]
	assert all(len(call) <= commons.ENTITY_BATCH for call in calls)


def test_candidates_keeps_only_the_designations_the_archive_answered_for(monkeypatch, tmp_path):
	"""The filter is the point: `audit pointed` answered for one of three gaps, not three."""
	stub(monkeypatch, wikidata={"entities": {
		"Q1": item(qid="Q1", codes=("SH 2-7",)),
		"Q2": item(qid="Q2", codes=("SH 2-8",)),
		"Q3": item(qid="Q3", codes=("RCW 141",)),
	}})
	gaps = gap_csv(tmp_path, ["SH 2-7,,Q1,Sh 2-7,,", "SH 2-8,,Q2,,,", "RCW 141,SH 2-20,Q3,,,"])
	pointed = [{"target": "SH 2-7", "verdict": "imaged", "archive_name": "SH-2-7"},
		{"target": "SH 2-8", "verdict": "no_pointed_data"}]
	rows = commons.candidates(gaps, targets=pointed)
	assert [row["designation"] for row in rows] == ["SH 2-7"], "a non-answer cannot shorten anything"
	assert rows[0]["gap"] == commons.G0_NO_ARTICLE
	assert rows[0]["archive_name"] == "SH-2-7"


def test_candidates_match_a_cross_identification(monkeypatch, tmp_path):
	"""`SH 2-20` is `RCW 141`: the archive audit resolved the item under its other designation."""
	stub(monkeypatch, wikidata={"entities": {"Q3": item(qid="Q3", codes=("RCW 141",))}})
	gaps = gap_csv(tmp_path, ["SH 2-20,RCW 141,Q3,,,"])
	rows = commons.candidates(gaps, targets=[{"target": "RCW 141", "verdict": "imaged"}])
	assert len(rows) == 1 and rows[0]["designation"] == "SH 2-20", (
		"the row keeps the designation the audit found it under")


def test_the_archive_row_is_joined_under_the_name_the_audit_used(monkeypatch, tmp_path):
	"""The gap is found under `SH 2-20`, the archive audit resolved it as `RCW 141`, and the row has
	to arrive with its verdict anyway — otherwise the candidate loses the data it was chosen for."""
	stub(monkeypatch, wikidata={"entities": {"Q3": item(qid="Q3", codes=("SH 2-20", "RCW 141"))}})
	gaps = gap_csv(tmp_path, ["SH 2-20,RCW 141,Q3,,,"])
	rows = commons.candidates(gaps, targets=[{"target": "RCW 141", "verdict": "imaged",
		"archive_name": "RCW-141", "rights": "PUBLIC"}])
	assert rows[0]["designation"] == "SH 2-20" and rows[0]["verdict"] == "imaged"
	assert rows[0]["archive_name"] == "RCW-141" and rows[0]["rights"] == "PUBLIC"


def test_a_target_list_without_verdicts_is_taken_as_given(monkeypatch, tmp_path):
	stub(monkeypatch, wikidata={"entities": {"Q1": item(qid="Q1", codes=("NGC 2174",))}})
	gaps = gap_csv(tmp_path, ["NGC 2174,,Q1,,,"])
	assert len(commons.candidates(gaps, targets=[{"target": "NGC 2174"}])) == 1


def test_candidates_round_trip_through_csv(monkeypatch, tmp_path):
	stub(monkeypatch,
		wikidata={"entities": {"Q1": item(qid="Q1", codes=("Sh 2-1",), article="Sh 2-1")}},
		files={"categorymembers": {"query": {}}},
		enwiki={"query": {"pages": {"1": {}}}})
	gaps = gap_csv(tmp_path, ["Sh 2-1,,Q1,,83.0,-4.0"])
	rows = commons.candidates(gaps, targets=[{"target": "Sh 2-1", "verdict": "imaged"}])
	path = commons.write_candidates(rows, tmp_path / "candidates.csv")
	with open(path, encoding="utf-8", newline="") as handle:
		written = list(csv.DictReader(handle))
	assert written[0]["gap"] == commons.G0_ARTICLE
	assert written[0]["ra"] == "83.0" and written[0]["n_category_files"] == "0"
	assert written[0]["article"] == "Sh 2-1" and written[0]["category_files"] == ""
