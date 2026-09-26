import numpy as np
import pytest

from astroproc.stretch import StretchParams, asinh_stretch, auto_params


def params(**kw):
	defaults = dict(shadow_clip=0.01, high_point=2.0, strength=8.0, background_level=0.03)
	defaults.update(kw)
	return StretchParams(**defaults)


def _patched_scene(rng, level):
	"""Background 0.02 plus one 8x8 patch at `level`, identical in all 3 channels."""
	x = np.full((3, 64, 64), 0.02, dtype=np.float32)
	x += rng.normal(0, 0.001, x.shape).astype(np.float32)
	x[:, 10:18, 10:18] = level
	return x


def test_shared_stretch_is_monotone():
	x = np.linspace(0.0, 5.0, 1000, dtype=np.float32)
	y, _ = asinh_stretch(x[None, :], params())
	assert np.all(np.diff(y[0]) >= 0)


def test_equal_linear_pixels_map_equal_across_channels():
	# the property that makes the colour-correctness argument: one shared stretch.
	# Equal linear values in different channels must land on equal display values.
	rng = np.random.default_rng(9)
	for level in (0.5, 2.0):
		x = _patched_scene(rng, level)
		y, _ = asinh_stretch(x, params())
		patch = y[:, 12:16, 12:16]
		assert np.allclose(patch[0], patch[1]) and np.allclose(patch[1], patch[2])


def test_below_shadow_clip_maps_to_black():
	x = np.zeros((3, 32, 32), dtype=np.float32)
	y, _ = asinh_stretch(x, params(background_level=0.0))
	assert np.all(y == 0.0)


def test_background_lands_on_target_level():
	rng = np.random.default_rng(7)
	x = rng.normal(0.02, 0.002, (3, 128, 128)).astype(np.float32)
	x[0, 64, 64] += 3.0  # one star so the clipped stats have a tail to reject
	y, shift = asinh_stretch(x, params())
	from astroproc.state import sky_stats
	med, _ = sky_stats(y)
	assert med == pytest.approx(0.03, abs=0.003)
	assert shift != 0.0


def test_auto_params_lies_above_sky():
	rng = np.random.default_rng(3)
	x = rng.normal(0.05, 0.005, (3, 128, 128)).astype(np.float32)
	p = auto_params(x)
	assert p.shadow_clip > 0.05
	assert p.high_point > p.shadow_clip
	assert p.describe().startswith("asinh shared across channels")


def test_hot_path_returns_independent_buffer():
	x = np.full((3, 8, 8), 0.5, dtype=np.float32)
	expected = asinh_stretch(x.copy(), params())[0].mean()
	y, _ = asinh_stretch(x, params())
	x[:] = 0.0  # mutating the input afterwards must not touch the output
	assert y.mean() == pytest.approx(float(expected))
