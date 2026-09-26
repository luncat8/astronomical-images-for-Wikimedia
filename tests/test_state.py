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
