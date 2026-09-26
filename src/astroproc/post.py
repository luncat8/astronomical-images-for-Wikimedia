"""Presentation-version post-processing (plan §7.7) and QC (§7.8).

Everything here is optional, ordered conservatively, and recorded. The data version is
exported before any of this runs (plan §3.2 fork point).
"""

import numpy as np
from scipy import ndimage

from .stretch import asinh_stretch

# Rec.709 luma weights; einsum keeps this allocation-light for (3, H, W) arrays
LUMA_WEIGHTS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def luma(rgb01):
	return np.einsum("i...,i->...", rgb01, LUMA_WEIGHTS)


def chroma_denoise(rgb01, strength=0.5):
	"""Median-filter the chroma channels only — kills colour speckle without plastic
	luminance. strength 0..1 blends the filtered chroma back. Y = Rec.709 luma,
	Cb = B - Y, Cr = R - Y; G is recovered exactly from the inverse relations."""
	if strength <= 0:
		return rgb01
	y = luma(rgb01)
	cb = rgb01[2] - y
	cr = rgb01[0] - y
	cb = np.float32(strength) * ndimage.median_filter(cb, size=3) + np.float32(1 - strength) * cb
	cr = np.float32(strength) * ndimage.median_filter(cr, size=3) + np.float32(1 - strength) * cr
	out = np.empty_like(rgb01)
	out[0] = y + cr
	out[1] = y - np.float32(0.2126 / 0.7152) * cr - np.float32(0.0722 / 0.7152) * cb
	out[2] = y + cb
	np.clip(out, 0.0, 1.0, out=out)
	return out


def hdr_core_blend(linear_rgb, presentation, sat_mask, params_short, feather=6.0):
	"""Blend a low-lift stretch into saturated cores (plan §7.7: required for hard cores)."""
	short, _ = asinh_stretch(linear_rgb, params_short)
	mask = ndimage.gaussian_filter(sat_mask.astype(np.float32), feather)
	mask = np.clip(mask, 0.0, 1.0)
	return presentation * (1.0 - mask) + short * mask


def saturate(rgb01, factor):
	"""Uniform saturation around Rec.709 luma; oversaturation is a listed defect (plan §10)."""
	if factor == 1.0:
		return rgb01
	y = luma(rgb01)
	out = y + np.float32(factor) * (rgb01 - y[None, :, :])
	np.clip(out, 0.0, 1.0, out=out)
	return out


def _median_profile(lum, mask, axis):
	"""Per-row/col median ignoring masked (bright) pixels; short gaps interpolated."""
	masked = np.where(mask, np.nan, lum)
	profile = np.nanmedian(masked, axis=axis)
	valid = np.nonzero(np.isfinite(profile))[0]
	if valid.size == 0:
		return np.zeros(profile.size, dtype=np.float64)
	return np.interp(np.arange(profile.size), valid, profile[valid])


def banding_check(rgb01, bright_percentile=98.0, trend_window=15):
	"""Row/column banding amplitude, in 8-bit levels (plan §7.8).

	Row/col medians with star cores excluded (bright percentile) and the smooth sky
	trend removed — what survives is banding. Human confirmation still happens at
	100% zoom in the faint outskirts.
	"""
	lum = luma(rgb01) * 255.0
	bright = lum > np.percentile(lum, bright_percentile)
	if bright.all():
		return {"ok": True, "row_levels": 0.0, "col_levels": 0.0, "statement": "no faint area to measure"}
	row_med = _median_profile(lum, bright, axis=1)
	col_med = _median_profile(lum, bright, axis=0)
	window = min(trend_window, max(3, lum.shape[0] // 8) | 1)
	row_amp = float(np.std(row_med - ndimage.uniform_filter1d(row_med, window)))
	col_amp = float(np.std(col_med - ndimage.uniform_filter1d(col_med, window)))
	worst = max(row_amp, col_amp)
	return {
		"ok": worst <= 1.0,
		"row_levels": row_amp,
		"col_levels": col_amp,
		"statement": f"banding amplitude {worst:.2f} 8-bit levels "
		             f"({'ok' if worst <= 1.0 else 'CHECK at 100%: banding likely visible'})",
	}


def chromatic_aberration_metric(rgb01, gradient_threshold=0.03):
	"""Purple-fringing measure on strong luminance edges (plan §7.7 lists it as a defect):
	excess of (R+B)/2 over G at edge pixels — the signature of lateral colour fringing."""
	lum = luma(rgb01)
	gy, gx = np.gradient(lum)
	edges = np.hypot(gx, gy) > gradient_threshold
	if np.count_nonzero(edges) < 50:
		return {"ok": True, "fringe_rb": 0.0, "statement": "no strong edges to measure"}
	fringe = rgb01[0] + rgb01[2] - np.float32(2.0) * rgb01[1]
	value = float(np.median(np.abs(fringe[edges])))
	return {
		"ok": value < 0.05,
		"fringe_rb": value,
		"statement": f"median (R+B)/2-G excess on edges {value:.4f} "
		             f"({'ok' if value < 0.05 else 'fringing? check'})",
	}
