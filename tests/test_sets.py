"""The archive-first axis (plan §6.3, §6.4 method 4), with the cone search replaced by fixtures.

The rows are the shape the 2026-09-26 live run produced, because the mistakes this module is built
against were made on real ones: `SH 2-252 F` images as `NGC-2174`, `SH 2-7`'s nearest HST pointing
is eight fields away from the object, and a `CIRCLE`/`POLYGON` footprint is the only thing that
tells a 29" ACS/HRC frame from a 187" WFC3/IR one in a table where both are "a filter set".
"""

import csv

from astroproc.audit import mast, sets
from astroproc.audit.sets import colour_sets, write_sets

# `SH 2-252 F`: ra/dec as the resolver returned them; the field is the real WFC3/IR drizzle size.
SH2_252F = {"name": "SH 2-252 F", "ra": 92.2930, "dec": 20.4800}


def box_at(ra, dec, arcsec):
	"""A square footprint of `arcsec` on the sky, centred where the pointing was."""
	import math

	half_ra = arcsec / 7200 / math.cos(math.radians(dec))
	half_dec = arcsec / 7200
	return (f"POLYGON {ra - half_ra} {dec + half_dec} {ra + half_ra} {dec + half_dec} "
		f"{ra + half_ra} {dec - half_dec} {ra - half_ra} {dec - half_dec} {ra - half_ra} {dec + half_dec}")


def observation(**kwargs):
	row = {
		"collection": "HST", "instrument": "WFC3/IR", "filters": "F105W", "obs_id": "ichx02020",
		"target_name": "NGC-2174", "region": box_at(92.2930, 20.4800, 187), "proposal": "13623",
		"pi": "Levay, Zolt",
		"public": "2014-05-19", "exptime": "1200.0", "rights": "PUBLIC",
	}
	return {**row, **kwargs}


def with_cone(monkeypatch, *observations):
	monkeypatch.setattr(mast, "_cone", lambda coord, radius, collections: list(observations))


def test_three_filters_in_one_program_are_a_colour_set(monkeypatch):
	with_cone(monkeypatch,
		observation(filters="F105W", exptime="1200.0"),
		observation(filters="F125W", obs_id="ichx02030", exptime="1400.0"),
		observation(filters="F160W", obs_id="ichx02040", exptime="1500.0"))
	row = colour_sets([SH2_252F], since="2014-01-01")[0]
	assert row["verdict"] == sets.COLOUR_SET
	assert row["n_filters"] == 3 and row["filters"] == "F105W;F125W;F160W"
	assert row["n_exposures"] == 3 and row["exptime_s"] == 1500.0
	assert row["archive_name"] == "NGC-2174", "the name that finds the Commons file goes in the row"
	assert row["public"] == "2014-05-19", "the set is usable when its last exposure is public"
	assert row["fov_arcsec"] == "187x187", "the frame of the deepest exposure, not the diagonal"


def test_a_set_is_one_program_with_one_detector(monkeypatch):
	"""F105W and F160W of one program are a set of two; a second program with one more filter is a
	set of one. Merging them would invent a composite the archive never observed together."""
	with_cone(monkeypatch,
		observation(filters="F105W", proposal="13623"),
		observation(filters="F160W", proposal="13623"),
		observation(filters="F814W", proposal="99999", instrument="ACS/WFC", obs_id="j99901"))
	rows = colour_sets([SH2_252F])
	assert [row["verdict"] for row in rows] == [sets.TOO_FEW_FILTERS] * 2
	assert sorted((row["n_filters"] for row in rows), reverse=True) == [2, 1]
	assert rows[0]["filters"] == "F105W;F160W"


def test_two_narrowbands_can_be_enough_when_the_caller_says_so(monkeypatch):
	with_cone(monkeypatch,
		observation(filters="F105W"), observation(filters="F160W", obs_id="ichx02030"))
	assert colour_sets([SH2_252F], min_filters=3)[0]["verdict"] == sets.TOO_FEW_FILTERS
	row = colour_sets([SH2_252F], min_filters=2)[0]
	assert row["verdict"] == sets.COLOUR_SET and row["n_filters"] == 2


def test_release_window_keeps_older_sets_visible_as_a_verdict(monkeypatch):
	"""A window that hides everything must not read as "no data": the old set keeps its row."""
	with_cone(monkeypatch, observation(filters="F105W"), observation(filters="F125W", obs_id="b"),
		observation(filters="F160W", obs_id="c"))
	rows = colour_sets([SH2_252F], since="2024-01-01", min_filters=2)
	assert [row["verdict"] for row in rows] == [sets.OLD_RELEASE]
	assert rows[0]["n_filters"] == 3, "the filters are still reported — the data exists, it is not new"


def test_unknown_release_date_is_not_old(monkeypatch):
	with_cone(monkeypatch, observation(filters="F105W", public=""),
		observation(filters="F125W", obs_id="b", public=""))
	row = colour_sets([SH2_252F], since="2024-01-01", min_filters=2)[0]
	assert row["verdict"] == sets.COLOUR_SET and row["public"] == ""


def test_a_pointing_that_misses_is_not_a_covering_set(monkeypatch):
	"""`SH 2-7`: 3.84' from a 29" field is eight fields of empty sky, whatever the cone radius."""
	far = observation(region=box_at(92.2930, 20.4800 + 0.064, 29), filters="F105W",
		instrument="ACS", obs_id="j8ga01hzq")
	with_cone(monkeypatch, far)
	row = colour_sets([SH2_252F], min_filters=2)[0]
	assert row["verdict"] == sets.MISSED and row["n_covering"] == 0 and row["n_other"] == 0


def test_acquisition_and_non_imaging_modes_are_counted_not_used(monkeypatch):
	with_cone(monkeypatch,
		observation(instrument="STIS/CCD", obs_id="findchart"),
		observation(instrument="NIRSPEC/IFU", collection="JWST", obs_id="spectrum"))
	row = colour_sets([SH2_252F], min_filters=2)[0]
	assert row["verdict"] == sets.NO_POINTED_DATA and row["n_other"] == 2
	all_modes = colour_sets([SH2_252F], min_filters=2, imaging_only=False)
	assert {row["instrument"] for row in all_modes} == {"STIS/CCD", "NIRSPEC/IFU"}
	assert all(row["n_filters"] == 1 for row in all_modes), "a finding chart is one filter, not colour"


def test_unreadable_footprint_is_its_own_verdict(monkeypatch):
	with_cone(monkeypatch, observation(region="--"))
	row = colour_sets([SH2_252F], min_filters=2)[0]
	assert row["verdict"] == sets.UNREADABLE, "not covering, and not 'the archive has nothing here'"


def test_target_without_coordinates_is_reported_not_dropped():
	rows = colour_sets([{"name": "SH 2-106 A", "ra": "", "dec": ""}])
	assert rows == [{"target": "SH 2-106 A", "verdict": sets.NO_COORDINATES}]


def test_empty_target_list_is_an_error():
	import pytest

	with pytest.raises(SystemExit):
		colour_sets([])


def test_filters_cell_with_several_names_counts_distinct_filters(monkeypatch):
	with_cone(monkeypatch,
		observation(filters="F105W;F125W"), observation(filters="F125W", obs_id="b"),
		observation(filters="CLEAR", obs_id="c"))
	row = colour_sets([SH2_252F], min_filters=2)[0]
	assert row["filters"] == "F105W;F125W" and row["n_filters"] == 2, "CLEAR is not a filter"


def test_rows_round_trip_through_csv(monkeypatch, tmp_path):
	with_cone(monkeypatch, observation(filters="F105W"), observation(filters="F125W", obs_id="b"),
		observation(filters="F160W", obs_id="c"))
	path = write_sets(colour_sets([SH2_252F], since="2014-01-01"), tmp_path / "sets.csv")
	with open(path, encoding="utf-8", newline="") as handle:
		rows = list(csv.DictReader(handle))
	assert len(rows) == 1
	assert rows[0]["verdict"] == sets.COLOUR_SET and rows[0]["filters"] == "F105W;F125W;F160W"
	assert rows[0]["archive_name"] == "NGC-2174" and rows[0]["n_filters"] == "3"
