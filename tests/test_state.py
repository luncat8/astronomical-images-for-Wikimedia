import numpy as np
import pytest

from astroproc.state import classify, inspect_file

from synth import make_scene


def test_linear_scene_classifies_linear():
	channels, _ = make_scene()
	report = classify(channels["Halpha"])
	assert report.verdict == "linear"
	assert report.core_fraction > 0.8   # star + galaxy wings live outside the core
	assert report.median_fraction < 0.005


def test_stretched_scene_classifies_stretched():
	channels, _ = make_scene()
	# what a processed preview product looks like: gamma-compressed, background lifted
	stretched = np.clip((channels["Halpha"] - 100.0) / 300.0, 0.0, 1.0) ** 0.4
	report = classify(stretched)
	assert report.verdict == "stretched"
	assert report.median_fraction > 0.02


def test_inspect_file_reports_provenance_and_saturation(tmp_path):
	from synth import write_channels
	channels, _ = make_scene()
	paths = write_channels(channels, tmp_path)
	report = inspect_file(paths["Halpha"])
	assert report.verdict == "linear"
	assert report.provenance["FILTER"] == "Halpha"
	assert report.sat_limit == pytest.approx(60000.0)
	assert report.saturated_count >= 1  # the planted saturated star


def test_sky_stats_recovery():
	channels, _ = make_scene()
	from astroproc.state import sky_stats
	med, std = sky_stats(channels["OIII"])
	assert med == pytest.approx(90.0, abs=2.0)
	assert 2.0 < std < 15.0


def test_median_fraction_metric_uses_percentile_anchor():
	# regression: metric must compare sky to the p0.1..p99.9 span, not be identically 0
	img = np.full((64, 64), 10.0, dtype=np.float32)
	img[10, 10] = 5000.0
	report = classify(img)
	assert report.median_fraction == pytest.approx(0.0, abs=0.01)


def test_blank_pixels_do_not_make_the_verdict_silently_wrong():
	"""Dithered and mosaicked products carry NaN coverage, and np.percentile does not skip it."""
	img = np.full((128, 128), 100.0, dtype=np.float32)
	img[40:80, 40:80] = np.nan
	img[0, 0] = 5000.0
	report = classify(img)
	assert report.invalid_fraction == pytest.approx(1600 / 16384, abs=0.001)
	assert np.isfinite(report.median_fraction), "the decision metric must be a number"
	assert report.verdict == "linear"
	assert any("non-finite" in note for note in report.notes)


def test_stretched_data_behind_blank_pixels_still_reads_stretched():
	"""The regression that matters: with NaN present the old metric reported NaN, and NaN > 0.02
	is False, so stretched data was labelled linear."""
	channels, _ = make_scene()
	img = np.clip((channels["Halpha"] - 100.0) / 300.0, 0.0, 1.0) ** 0.4
	img[40:80, 40:80] = np.nan
	assert classify(img).verdict == "stretched"


def nebula_frame(size=128, sky=100.0, peak=4000.0, sigma=1.2):
	"""A frame whose subject fills it: broad distribution, no sky peak, median high in the span.

	That is the shape of a real nebula image (measured: WFC3/IR drz of NGC 2174, median/span
	0.245), and it is what makes the histogram argument uninformative.
	"""
	axis = np.linspace(-1.0, 1.0, size)
	yy, xx = np.meshgrid(axis, axis, indexing="ij")
	radius = np.hypot(yy, xx)
	return (sky + peak * np.exp(-(radius / sigma) ** 2)).astype(np.float32)


def test_pipeline_provenance_outranks_a_sky_less_histogram():
	"""A nebula that fills the frame has no sky peak, so only the header can decide."""
	img = nebula_frame()
	header = {"BUNIT": "ELECTRONS/S", "NCOMBINE": 2, "INSTRUME": "WFC3"}
	report = classify(img, header=header)
	assert report.verdict == "linear", "a drz/drc/i2d product is linear by construction"
	assert any("linear by construction" in note for note in report.notes)


def test_no_pipeline_provenance_keeps_the_histogram_verdict():
	"""A preview image with no physical unit is still judged by the histogram and still refused."""
	img = nebula_frame()
	assert classify(img).median_fraction > 0.02, "the histogram alone must still read stretched"
	assert classify(img, header={"BUNIT": "DN"}).verdict == "stretched"
	assert classify(img).verdict == "stretched"
