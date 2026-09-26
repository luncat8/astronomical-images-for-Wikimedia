import numpy as np
import pytest

from astroproc.background import match_sky, sky_gains, subtract_sky
from astroproc.state import sky_stats

from synth import SKY_LEVELS, THROUGHPUT, make_scene


def test_subtract_sky_removes_level():
	channels, _ = make_scene()
	sub, level = subtract_sky(channels["Halpha"])
	assert level == pytest.approx(120.0, abs=2.0)
	med, _ = sky_stats(sub)
	assert abs(med) < 0.5


def test_sky_gains_equalise_levels():
	gains = sky_gains(SKY_LEVELS, "Halpha")
	assert gains["OIII"] == pytest.approx(120.0 / 90.0)
	assert gains["Halpha"] == pytest.approx(1.0)


def test_sky_gains_degenerate_anchor():
	assert sky_gains({"a": 0.0, "b": 5.0}, "a") == {}


def test_match_sky_end_to_end():
	channels, _ = make_scene()
	# plant a white patch: equal true flux in every channel
	for name in channels:
		channels[name][50:58, 50:58] += np.float32(500.0 * THROUGHPUT[name])
	matched, record = match_sky(channels, "Halpha")
	# skies are subtracted per channel, so the residual background is ~0 everywhere;
	# the gains exist to restore consistent object-flux scale (relative throughput)
	med, _ = sky_stats(matched["OIII"])
	assert abs(med) < 0.5
	assert record["anchor"] == "Halpha"
	# gains come from measured skies, so allow measurement noise
	assert record["gains (sky match x throughput)"]["OIII"] == pytest.approx(120.0 / 90.0, rel=0.01)
	# the white patch keeps near-equal channel fluxes after the scale correction
	patch = [matched[name][52:56, 52:56].mean() for name in ("Halpha", "OIII", "SII")]
	assert max(patch) / min(patch) == pytest.approx(1.0, abs=0.1)


def test_match_sky_with_throughput_factor():
	channels, _ = make_scene()
	matched, record = match_sky(channels, "Halpha", throughput={"OIII": 2.0})
	assert record["gains (sky match x throughput)"]["OIII"] == pytest.approx(2 * 120.0 / 90.0, rel=0.01)


def test_match_sky_skyless_product_gets_gain_one():
	zeroed = {name: img - level for name, (img, level) in zip(
		("a", "b"), ((np.full((32, 32), 7.0, dtype=np.float32), 7.0),
		             (np.full((32, 32), 30.0, dtype=np.float32), 30.0)))}
	matched, record = match_sky(zeroed, "a")
	assert all(g == 1.0 for g in record["gains (sky match x throughput)"].values())
