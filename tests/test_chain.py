"""The tail of the 0.B loop, driven through the CLI (plan §16.4): gap CSV -> pointed CSV ->
candidates CSV -> dossier.

Each producer's own logic is tested in its own file; this is the wiring between them, which is
where a chain leaks: the CSV columns one command writes and the next one reads, the verdicts that
have to survive a round-trip as strings, and the hard gate that has to stop a candidate the audit
liked. `SH 2-20`/`RCW 141` is the case: the audit calls it a gap, the archive images it, and
Commons already has the file under the other designation.
"""

import csv
import json

import pytest

from astroproc import cli
from astroproc.audit import commons

GAPS = """designation,aliases,item,label,ra,dec
SH 2-20,RCW 141,Q1,,,
SH 2-7,,Q2,Sh 2-7,83.0,-4.0
"""
POINTED = """target,archive_name,verdict,n_pointed,n_covering,n_other,sep_arcsec,obs_id,instrument,filters,fov_arcsec,proposal,pi,public,rights
SH 2-20,RCW-141,imaged,3,1,0,0.0,o6d601,ACS/WFC,F606W;F814W,202x202,10775,PI,PUBLIC,PUBLIC
SH 2-7,SH-2-7,no_pointed_data,0,0,1,,,,,,,,,
"""


def write(tmp_path, name, text):
	path = tmp_path / name
	path.write_text(text, encoding="utf-8")
	return path


def item(qid, codes, category="", article=""):
	entity = {"id": qid, "claims": {"P528": [{"mainsnak": {"datavalue": {"value": code}}} for code in codes]},
		"sitelinks": {}}
	if category:
		entity["sitelinks"]["commonswiki"] = {"title": category}
	if article:
		entity["sitelinks"]["enwiki"] = {"title": article}
	return entity


def stub_wikidata(monkeypatch, entities, category_files=(), lead=""):
	def fake_get(url, **params):
		if url == commons.WIKIDATA:
			return {"entities": entities}
		if url == commons.ENWIKI:
			return {"query": {"pages": {"1": {}}}}
		if params.get("list") == "categorymembers":
			return {"query": {"categorymembers": [{"title": title} for title in category_files]}}
		return {"query": {}}

	monkeypatch.setattr(commons, "get", fake_get)


def test_commons_then_score_over_the_audit_files(tmp_path, monkeypatch, capsys):
	"""`SH 2-20` comes out covered (Commons has `RCW 141`), `SH 2-7` stays a G0 with no lead image."""
	stub_wikidata(monkeypatch,
		{"Q1": item("Q1", ("SH 2-20", "RCW 141"), category="Category:RCW 141", article="RCW 141"),
			"Q2": item("Q2", ("SH 2-7",), article="Sh 2-7")},
		category_files=("File:RCW 141.jpg", "File:RCW 141 (cropped).jpg"))
	gaps = write(tmp_path, "gaps.csv", GAPS)
	pointed = write(tmp_path, "pointed.csv", POINTED)
	candidates = tmp_path / "candidates.csv"

	assert cli.main(["audit", "commons", str(gaps), "--targets", str(pointed), "--out", str(candidates)]) == 0
	report = capsys.readouterr().out
	assert "1 candidate(s) checked of 2 gap row(s)" in report, (
		"the archive answered for one of the two gaps, and the other is not a 522-request question")
	assert "SH 2-20" in report and commons.COVERED in report
	assert "2 file(s) in Category:RCW 141" in report
	assert "0 still a gap, 1 already illustrated" in report

	with candidates.open(encoding="utf-8", newline="") as handle:
		rows = {row["designation"]: row for row in csv.DictReader(handle)}
	assert rows["SH 2-20"]["archive_name"] == "RCW-141", "the pointed row is joined onto the candidate"
	assert rows["SH 2-20"]["n_category_files"] == "2"

	assert cli.main(["audit", "score", str(candidates), "--set", "3=2"]) == 0
	scored = capsys.readouterr().out
	assert scored.count("Object:") == 1, "one dossier per candidate"
	assert "drop (hard gate)" in scored, "the covered candidate cannot be pursued further"


def test_all_targets_checks_a_curated_shortlist_whatever_the_archive_said(tmp_path, monkeypatch, capsys):
	"""`Sh 2-7` is a G0 with an article and no lead image — and the HST pointing missed it. The
	archive verdict cannot decide a ground-based opportunity, so the operator can overrule it."""
	stub_wikidata(monkeypatch,
		{"Q1": item("Q1", ("SH 2-20", "RCW 141"), category="Category:RCW 141"),
			"Q2": item("Q2", ("SH 2-7",), article="Sh 2-7")},
		category_files=("File:RCW 141.jpg",))
	gaps = write(tmp_path, "gaps.csv", GAPS)
	pointed = write(tmp_path, "pointed.csv", POINTED)
	candidates = tmp_path / "candidates.csv"
	cli.main(["audit", "commons", str(gaps), "--targets", str(pointed), "--all-targets",
		"--out", str(candidates)])
	report = capsys.readouterr().out
	assert "2 candidate(s) checked" in report
	assert commons.COVERED in report and commons.G0_ARTICLE in report
	with candidates.open(encoding="utf-8", newline="") as handle:
		rows = {row["designation"]: row for row in csv.DictReader(handle)}
	assert rows["SH 2-7"]["verdict"] == "no_pointed_data", "the verdict travels with the candidate"
	assert rows["SH 2-7"]["gap"] == commons.G0_ARTICLE


def test_score_can_write_the_dossiers_to_a_file(tmp_path, monkeypatch):
	stub_wikidata(monkeypatch, {"Q2": item("Q2", ("SH 2-7",), article="Sh 2-7")})
	gaps = write(tmp_path, "gaps.csv", "designation,aliases,item,label,ra,dec\nSH 2-7,,Q2,Sh 2-7,83.0,-4.0\n")
	candidates = tmp_path / "candidates.csv"
	cli.main(["audit", "commons", str(gaps), "--out", str(candidates)])
	out = tmp_path / "dossiers.txt"
	assert cli.main(["audit", "score", str(candidates), "--out", str(out)]) == 0
	text = out.read_text(encoding="utf-8")
	assert "SH 2-7" in text and "Score:" in text


def test_sets_rows_feed_the_commons_check_and_the_score(tmp_path, monkeypatch, capsys):
	"""`audit sets` output is the other producer `audit commons` accepts: same `target` column."""
	stub_wikidata(monkeypatch, {"Q3": item("Q3", ("RCW 141",))})
	gaps = write(tmp_path, "gaps.csv", "designation,aliases,item,label,ra,dec\nRCW 141,SH 2-20,Q3,,,\n")
	sets_csv = write(tmp_path, "sets.csv", "target,verdict,archive_name,instrument,filters,n_filters\n"
		"RCW 141,colour_set,RCW-141,WFC3/IR,F105W;F125W;F160W,3\n")
	candidates = tmp_path / "candidates.csv"
	cli.main(["audit", "commons", str(gaps), "--targets", str(sets_csv), "--out", str(candidates)])
	rows = list(csv.DictReader(candidates.open(encoding="utf-8")))
	assert rows[0]["designation"] == "RCW 141" and rows[0]["filters"] == "F105W;F125W;F160W"
	cli.main(["audit", "score", str(candidates)])
	assert "F105W, F125W, F160W" in capsys.readouterr().out


def test_score_rejects_a_pure_noise_call(tmp_path):
	path = write(tmp_path, "candidates.csv", "designation,item\n")
	with pytest.raises(SystemExit):
		cli.main(["audit", "score", str(path)])


def test_commons_can_be_run_without_a_target_list(tmp_path, monkeypatch, capsys):
	"""A hand-made shortlist is taken as given — the operator asked for those rows deliberately."""
	stub_wikidata(monkeypatch, {"Q3": item("Q3", ("RCW 141",))})
	gaps = write(tmp_path, "gaps.csv", "designation,aliases,item,label,ra,dec\nRCW 141,SH 2-20,Q3,,,\n")
	assert cli.main(["audit", "commons", str(gaps)]) == 0
	assert "RCW 141" in capsys.readouterr().out


def test_the_json_of_a_commons_row_keeps_its_types(tmp_path, monkeypatch):
	"""The candidate rows are JSON-serialisable as they stand — the CSV is the only stringly layer."""
	stub_wikidata(monkeypatch, {"Q2": item("Q2", ("SH 2-7",), article="Sh 2-7")})
	gaps = write(tmp_path, "gaps.csv", "designation,aliases,item,label,ra,dec\nSH 2-7,,Q2,Sh 2-7,83.0,-4.0\n")
	pointed = write(tmp_path, "pointed.csv", POINTED)
	rows = commons.candidates(gaps, targets=pointed, searched=True, answered_only=False)
	assert json.loads(json.dumps(rows)), "the row is plain data, not objects"
	assert rows[0]["text_hits"] == [] and rows[0]["category_files"] == []
