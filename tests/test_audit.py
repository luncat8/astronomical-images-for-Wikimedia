import pytest

from astroproc.audit.score import RUBRIC, Score, render_dossier
from astroproc.audit.sparql import QUERY, parse_response


def test_sparql_query_parametrisation():
	text = QUERY.format(prefix="Sh2 ", limit=50)
	assert 'STRSTARTS(?cat, "Sh2 ")' in text
	assert "FILTER NOT EXISTS { ?item wdt:P18 ?img }" in text
	assert "LIMIT 50" in text


def test_sparql_parse_rows():
	payload = {"results": {"bindings": [
		{
			"item": {"value": "http://www.wikidata.org/entity/Q123"},
			"itemLabel": {"value": "Sh2-1"},
			"cat": {"value": "Sh2 1"},
			"coords": {"value": "Point(150.1 2.2)"},
		},
		{
			"item": {"value": "http://www.wikidata.org/entity/Q124"},
			"itemLabel": {"value": "Sh2-2"},
			"cat": {"value": "Sh2 2"},
		},
	]}}
	rows = parse_response(payload)
	assert len(rows) == 2
	assert rows[0]["ra"] == 150.1 and rows[0]["dec"] == 2.2
	assert "ra" not in rows[1]


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
