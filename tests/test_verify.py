import numpy as np
import pytest

from astroproc.verify import detect_stars, orientation_report, star_colour_report

from synth import STAR_COLOURS, THROUGHPUT, make_scene, make_wcs


def test_orientation_north_up_when_wcs_aligned():
	wcs = make_wcs((200, 300))
	report = orientation_report(wcs, (200, 300))
	assert report["ok"]
	assert abs(report["north_angle_deg"]) < 2.0        # +Dec is +y (up)
	assert abs(report["east_angle_deg"] + 90.0) < 2.0  # +RA is -x (left)
	assert report["handedness"] == "normal"


def test_orientation_detects_mirror():
	wcs = make_wcs((200, 300), mirror=True)
	report = orientation_report(wcs, (200, 300))
	assert report["ok"]
	assert report["handedness"] == "MIRRORED"


def test_orientation_detects_rotation():
	wcs = make_wcs((200, 300), rotation_deg=30.0)
	report = orientation_report(wcs, (200, 300))
	assert report["ok"]
	# camera rotated 30 deg CW on sky -> north appears rotated on the detector
	assert 25.0 < abs(report["north_angle_deg"]) < 35.0
	assert abs(report["rotation_to_n_up_deg"]) > 20.0


def test_detect_stars_finds_planted_stars():
	channels, truth = make_scene(n_stars=30)
	stack = np.stack([channels[n] for n in ("Halpha", "OIII", "SII")])
	coords, fluxes = detect_stars(stack - 105.0, n_stars=32)
	assert fluxes.shape[0] >= 20
	# brightest detected stars coincide with planted positions
	planted = {(y, x) for y, x, f in truth["stars"] if f > 1e4}
	indices = {(int(r), int(c)) for r, c in coords[:10]}
	assert len(indices & planted) >= 8


def test_star_colour_report_sees_varied_colours():
	channels, truth = make_scene(n_stars=60)
	stack = np.stack([channels[n] for n in ("Halpha", "OIII", "SII")])
	_, fluxes = detect_stars(stack - 105.0, n_stars=64)
	report = star_colour_report(fluxes)
	assert report["ok"], report["statement"]
	assert report["blue_fraction"] > 0.05
	assert report["red_fraction"] > 0.05


def test_star_colour_report_collapses_for_monochrome():
	# what a pure single-band tint does: every star identical -> the check must fail
	fluxes = np.tile([100.0, 100.0, 100.0], (20, 1))
	report = star_colour_report(fluxes)
	assert not report["ok"]
	assert "collapsed" in report["statement"]


def test_star_colours_recover_ground_truth():
	"""The pipeline-order correctness claim, verified: after sky subtraction with
	throughput correction, star R/B ratios cluster at the planted classes."""
	channels, truth = make_scene(n_stars=60)
	names = ("Halpha", "OIII", "SII")
	stack = np.stack([channels[n] / THPUT[n] for n in names]) - 110.0
	_, fluxes = detect_stars(stack, n_stars=64)
	ratio = fluxes[:, 0] / np.maximum(fluxes[:, 2], 1e-9)
	for cls, (r, g, b) in STAR_COLOURS.items():
		expected = r / b
		near = np.count_nonzero(np.abs(ratio - expected) < 0.35 * expected)
		assert near >= 3, f"{cls} stars not recovered: expected R/B ~ {expected:.2f}"


THPUT = {"Halpha": 1.0, "OIII": 0.8, "SII": 0.9}
