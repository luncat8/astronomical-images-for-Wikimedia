"""Verification (plan §7.6): orientation from WCS, star-colour plausibility.

The highest-value, lowest-cost step in the pipeline: an upside-down or mirrored
image is an immediate visible reject, and uniform star colour is the biggest visual
tell of amateur processing. Both checks report their evidence.
"""

import numpy as np
from scipy import ndimage

from .state import sky_stats


def orientation_report(wcs, shape):
	"""Where are N and E on the detector, and what rotation reaches N-up/E-left?

	Convention: FITS row 0 is at the bottom in display, so 'up' is +y (rows).
	Returns angles in degrees measured counter-clockwise from +y (up) toward +x (right).
	"""
	ny, nx = shape[-2:]
	cy, cx = (ny - 1) / 2.0, (nx - 1) / 2.0
	step = max(1.0, min(ny, nx) / 200.0)
	px = [cx, cx, cx, cx + step]
	py = [cy, cy + step, cy, cy]
	ra, dec = wcs.all_pix2world(px, py, 0)

	def tangent(dr, dd):
		"""Small-angle tangent-plane offset in degrees: x toward +RA, y toward +Dec."""
		return np.array([(dr - ra[0]) * np.cos(np.deg2rad(dec[0])), dd - dec[0]])

	north = tangent(ra[1], dec[1])
	east = tangent(ra[3], dec[3])
	if not (np.any(north) and np.any(east)):
		return {"ok": False, "reason": "degenerate WCS vectors"}

	def angle_from_up(v):
		angle = float(np.degrees(np.arctan2(v[0], v[1])))  # 0 = up, +90 = right
		return 0.0 if abs(angle) < 0.05 else angle

	# standard display orientation (N up, E left) has det([north east]) > 0 and
	# mirrored data flips it
	handed = "normal" if np.linalg.det(np.array([north, east])) > 0 else "MIRRORED"
	rotation_to_n_up = -angle_from_up(north)
	rotation_to_n_up = 0.0 if abs(rotation_to_n_up) < 0.05 else rotation_to_n_up
	return {
		"ok": True,
		"north_angle_deg": angle_from_up(north),
		"east_angle_deg": angle_from_up(east),
		"handedness": handed,
		"rotation_to_n_up_deg": rotation_to_n_up,
		"statement": (
			f"north {angle_from_up(north):+.1f} deg from up, east {angle_from_up(east):+.1f} deg "
			f"from up, {handed}; rotate {rotation_to_n_up:+.1f} deg for N-up"
		),
	}


def detect_stars(linear_rgb, sat_mask=None, n_stars=64, sigma=5.0):
	"""Top-N unsaturated stars with per-channel aperture fluxes (3x3, sky already subtracted).

	Returns (coords (n, 2) as (row, col), fluxes (n, 3)).
	"""
	total = linear_rgb.sum(axis=0)
	sky, std = sky_stats(total)
	local_max = ndimage.maximum_filter(total, size=5, mode="nearest")
	mask = (total == local_max) & (total > sky + sigma * std)
	if sat_mask is not None:
		mask &= ~sat_mask
	rows, cols = np.nonzero(mask)
	if rows.size == 0:
		return np.empty((0, 2)), np.empty((0, 3))
	flux_total = total[rows, cols]
	order = np.argsort(flux_total)[::-1][:n_stars]
	rows, cols = rows[order], cols[order]

	h, w = total.shape
	fluxes = np.empty((rows.size, linear_rgb.shape[0]), dtype=np.float64)
	for c in range(linear_rgb.shape[0]):
		plane = linear_rgb[c]
		acc = np.zeros(rows.size)
		for dr in (-1, 0, 1):
			for dc in (-1, 0, 1):
				rr = np.clip(rows + dr, 0, h - 1)
				cc = np.clip(cols + dc, 0, w - 1)
				acc += plane[rr, cc]
		fluxes[:, c] = acc
	return np.stack([rows, cols], axis=1), fluxes


def star_colour_report(fluxes, blue_r_max=0.85, red_r_min=1.25, min_fraction=0.08):
	"""Are star colours varied and plausible (plan §8: 'stars show plausible, varied colour')?

	Uses the R/B flux ratio: blue-white stars < 1 < orange stars. A pure narrowband
	composite collapses every star to one colour — this check catches that.
	"""
	if fluxes.shape[0] < 3:
		return {"ok": False, "reason": "not enough stars detected", "n_stars": int(fluxes.shape[0])}
	b = np.maximum(fluxes[:, 2], 1e-12)
	ratio = fluxes[:, 0] / b
	blue = float(np.count_nonzero(ratio < blue_r_max)) / ratio.size
	red = float(np.count_nonzero(ratio > red_r_min)) / ratio.size
	iqr = float(np.subtract(*np.percentile(ratio, [75, 25])))
	ok = blue >= min_fraction and red >= min_fraction
	return {
		"ok": ok,
		"n_stars": int(ratio.size),
		"median_rb": float(np.median(ratio)),
		"iqr_rb": iqr,
		"blue_fraction": blue,
		"red_fraction": red,
		"statement": (
			f"R/B median {np.median(ratio):.2f}, IQR {iqr:.2f}, "
			f"blue {blue:.0%} / red {red:.0%} of stars -> "
			f"{'varied, plausible' if ok else 'SUSPECT: star colour collapsed'}"
		),
	}
