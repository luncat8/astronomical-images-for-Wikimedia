"""The pointed detector's decisions, made without the network (`mast._cone` is replaced).

The numbers are the ones the 2026-09-26 live run produced, because a detector that is only ever
tested on synthetic squares is exactly how `SH 2-252 F` came to be listed as a candidate when its
own observation is named `NGC-2174`.
"""

import csv
import math

import pytest

from astroproc.audit import mast
from astroproc.audit.mast import UNKNOWN, observation_roles, pointed, write_pointed

# The cone search the audit actually issued for `SH 2-7` (ra, dec of the resolved gap).
SH2_7 = {"name": "SH 2-7", "ra": 83.0, "dec": -4.0}
# `SH 2-252 F`: one WFC3/IR visit, 0.74' away, and the archive calls the object NGC-2174.
SH2_252F = {"name": "SH 2-252 F", "ra": 92.2930, "dec": 20.4800}


def observation(**kwargs):
	"""One MAST row as `_cone` returns it."""
	row = {
		"collection": "HST", "instrument": "WFC3/IR", "filters": "F105W", "obs_id": "ichx02020",
		"target_name": "NGC-2174", "region": BOX, "proposal": "13623", "pi": "Levay, Zolt",
		"public": "2014-05-19", "rights": "PUBLIC",
	}
	return {**row, **kwargs}


def box(ra, dec, width_arcsec, height_arcsec):
	"""A rectangular footprint as MAST writes it: a size on the sky, written in RA/Dec degrees."""
	half_width = width_arcsec / 7200 / math.cos(math.radians(dec))
	left, right = ra - half_width, ra + half_width
	bottom, top = dec - height_arcsec / 7200, dec + height_arcsec / 7200
	return f"POLYGON {left} {top} {right} {top} {right} {bottom} {left} {bottom} {left} {top}"


BOX = box(92.29930679, 20.48330624, 187, 187)  # the WFC3/IR drizzle footprint, 187" x 187"


def with_cone(monkeypatch, *observations):
	"""Point the detector at a fixed set of observations."""
	monkeypatch.setattr(mast, "_cone", lambda coord, radius, collections: list(observations))


def test_footprint_on_the_object_is_imaged(monkeypatch):
	with_cone(monkeypatch, observation())
	row = pointed([SH2_252F])[0]
	assert row["verdict"] == "imaged"
	assert row["n_covering"] == 1 and row["sep_arcsec"] == 0.0
	assert row["archive_name"] == "NGC-2174", "the archive's name is the one that finds the Commons file"
	assert row["fov_arcsec"] == "187x187"
	assert (row["proposal"], row["pi"], row["public"], row["rights"]) == (
		"13623", "Levay, Zolt", "2014-05-19", "PUBLIC")


def test_pointing_3_arcmin_away_does_not_image_the_object(monkeypatch):
	"""`SH 2-7`: closest HST pointing 3.84' from a 29" ACS/HRC field — eight fields of empty sky.

	MAST records an HRC exposure as instrument `ACS` with the channel in the filter name, so the
	detector is only distinguishable in the footprint — which is the reason the test reads `s_region`
	and not a table of field sizes.
	"""
	with_cone(monkeypatch, observation(instrument="ACS", filters="F814W", obs_id="j8ga01hzq",
		region=box(83.0, -4.0679, 29, 29), target_name="SH 2-7"))
	row = pointed([SH2_7])[0]
	assert row["verdict"] == "footprint_missed"
	assert row["sep_arcsec"] == pytest.approx(230, abs=5)
	assert row["n_pointed"] == 1 and row["n_covering"] == 0


def test_survey_and_non_imaging_modes_are_counted_not_counted_as_data(monkeypatch):
	with_cone(monkeypatch,
		observation(instrument="STIS/CCD", obs_id="findchart"),
		observation(instrument="COS/FUV", obs_id="spectrum"),
		observation(instrument="FGS/SIRTF", obs_id="guidance"),
		observation(instrument="WFC3/LR", obs_id="mode-this-table-does-not-know"))
	row = pointed([SH2_252F])[0]
	assert row["verdict"] == "no_pointed_data" and row["n_pointed"] == 0
	assert row["n_other"] == 4, "a finding chart must be visible, not silently dropped"


def test_all_modes_counts_acquisition_exposures(monkeypatch):
	with_cone(monkeypatch, observation(instrument="STIS/CCD", obs_id="findchart"))
	assert pointed([SH2_252F], imaging_only=False)[0]["n_pointed"] == 1
	assert pointed([SH2_252F])[0]["n_pointed"] == 0


def test_unreadable_footprint_is_not_a_missed_footprint(monkeypatch):
	with_cone(monkeypatch, observation(region="--"))
	row = pointed([SH2_252F])[0]
	assert row["verdict"] == "footprint_unreadable"
	assert row["sep_arcsec"] is None and row["fov_arcsec"] == "-"
	assert row["archive_name"] == "NGC-2174", "the name is still worth reading"


def test_closest_observation_is_the_one_reported(monkeypatch):
	near = observation(obs_id="near", region=box(92.29930679, 20.48330624, 0.0052, 0.0052))
	far = observation(obs_id="far", region=box(93.0, 21.0, 0.0052, 0.0052))
	with_cone(monkeypatch, far, near)
	row = pointed([SH2_252F])[0]
	assert row["obs_id"] == "near" and row["n_pointed"] == 2


def test_target_without_coordinates_is_reported_not_dropped(monkeypatch):
	with_cone(monkeypatch)
	rows = pointed([{"name": "SH 2-106 A", "ra": "", "dec": ""}])
	assert rows == [{"target": "SH 2-106 A", "verdict": "no_coordinates"}]


def test_empty_target_list_is_an_error():
	with pytest.raises(SystemExit):
		pointed([])


def test_roles_come_from_the_measured_table():
	assert observation_roles("HST", "WFC3/IR") == "imaging"
	assert observation_roles("HST", "STIS/CCD") == "acquisition"
	assert observation_roles("JWST", "NIRSPEC/IFU") == "spectroscopy"
	assert observation_roles("HST", "WFC3/LR") == UNKNOWN
	assert observation_roles("TESS", "Photometer") == UNKNOWN, "the table is for pointed missions only"


def test_rows_round_trip_through_csv(monkeypatch, tmp_path):
	with_cone(monkeypatch, observation())
	path = write_pointed(pointed([SH2_252F]), tmp_path / "pointed.csv")
	with open(path, encoding="utf-8", newline="") as handle:
		rows = list(csv.DictReader(handle))
	assert len(rows) == 1
	assert rows[0]["archive_name"] == "NGC-2174" and rows[0]["verdict"] == "imaged"
	assert rows[0]["fov_arcsec"] == "187x187" and rows[0]["sep_arcsec"] == "0.0"


def test_the_resolver_object_type_travels_with_the_target(monkeypatch, tmp_path):
	"""§6.2.1 measured `otype` as a free false-positive detector; it has to survive the chain."""
	with_cone(monkeypatch, observation())
	rows = pointed([{**SH2_252F, "otype": "HII"}])
	assert rows[0]["otype"] == "HII"
	path = write_pointed(rows, tmp_path / "pointed.csv")
	with open(path, encoding="utf-8", newline="") as handle:
		assert list(csv.DictReader(handle))[0]["otype"] == "HII"
	rows = pointed([{**SH2_252F, "otype": "PN"}])
	assert rows[0]["otype"] == "PN" and rows[0]["verdict"] == "imaged"
