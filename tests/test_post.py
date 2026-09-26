import numpy as np
import pytest

from astroproc.post import (
	banding_check,
	chroma_denoise,
	chromatic_aberration_metric,
	hdr_core_blend,
	saturate,
)
from astroproc.stretch import StretchParams, asinh_stretch


def test_chroma_denoise_removes_colour_speckle():
	rng = np.random.default_rng(5)
	lum = np.full((64, 64), 0.2, dtype=np.float32)
	speck = np.zeros((64, 64, 3), dtype=np.float32)
	speck[20, 20] = (0.0, 0.0, 0.5)  # isolated blue speck
	rgb = np.clip(speck + lum[..., None], 0, 1).transpose(2, 0, 1)
	cleaned = chroma_denoise(rgb, strength=1.0)
	assert cleaned[2, 20, 20] < rgb[2, 20, 20]  # speck reduced
	# luminance untouched: luma before == luma after (chroma-only operation)
	from astroproc.post import luma
	l_before = luma(rgb)
	l_after = luma(cleaned)
	assert np.mean(np.abs(l_before - l_after)) < 0.05


def test_chroma_denoise_identity_at_zero():
	rgb = np.random.default_rng(1).uniform(0, 1, (3, 16, 16)).astype(np.float32)
	assert chroma_denoise(rgb, 0.0) is rgb


def test_saturate_identity_at_one():
	rgb = np.random.default_rng(2).uniform(0, 1, (3, 16, 16)).astype(np.float32)
	assert saturate(rgb, 1.0) is rgb


def test_saturate_increases_spread():
	rgb = np.full((3, 8, 8), 0.3, dtype=np.float32)
	rgb[0] = 0.5
	more = saturate(rgb, 1.5)
	assert more[0].mean() > rgb[0].mean()
	np.testing.assert_allclose(more[1], more[2])


def test_banding_check_detects_planted_rows():
	rng = np.random.default_rng(3)
	img = np.full((3, 128, 128), 0.05, dtype=np.float32)
	img += rng.normal(0, 0.002, (3, 128, 128)).astype(np.float32)
	assert banding_check(img)["ok"]
	img[1, ::4, :] += 0.02  # strong row banding
	report = banding_check(img)
	assert not report["ok"]


def test_chromatic_aberration_metric_flags_fringing():
	rgb = np.full((3, 64, 64), 0.3, dtype=np.float32)
	# purple fringe: R and B both elevated against G on one side of a hard edge
	rgb[0, :, 32:] += 0.4
	rgb[2, :, 32:] += 0.4
	report = chromatic_aberration_metric(rgb)
	assert not report["ok"]


def test_hdr_core_blend_recovers_core_structure():
	rng = np.random.default_rng(4)
	x = np.full((3, 64, 64), 0.02, dtype=np.float32)
	x[:, 32, 32] = 50.0  # blazing core
	linear = x * 1000.0  # ADU scale
	p = StretchParams(shadow_clip=20.0, high_point=5000.0, strength=10.0, background_level=0.03)
	pres, _ = asinh_stretch(linear, p)
	sat = linear.max(axis=0) >= 40000.0
	assert sat.any()
	short = StretchParams(shadow_clip=40.0, high_point=5000.0, strength=10.0, background_level=0.03)
	blended = hdr_core_blend(linear, pres, sat, short, feather=2.0)
	# core is not a flat clipped blob: neighbour pixels keep gradient
	assert np.ptp(blended[:, 30:35, 30:35].max(axis=0)) > 0.0
	assert np.abs(blended - pres).max() > 0.0
