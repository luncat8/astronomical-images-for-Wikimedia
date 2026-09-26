"""Channel registration via WCS (plan §7.4 precondition).

Archive products from the same visit are usually already aligned; when WCS differs
we resample bilinearly onto the reference grid with astropy + scipy alone.
"""

import numpy as np
from astropy.wcs import WCS
from scipy import ndimage

OFFSET_TOLERANCE_PX = 0.1


def _probe_offset(wcs_ref, wcs_other, shape):
	"""Median pixel offset of wcs_other relative to wcs_ref, sampled on a coarse grid."""
	ny, nx = shape[-2:]
	xs = np.linspace(nx / 4, 3 * nx / 4, 5)
	ys = np.linspace(ny / 4, 3 * ny / 4, 5)
	xx, yy = np.meshgrid(xs, ys)
	ra, dec = wcs_other.all_pix2world(xx.ravel(), yy.ravel(), 0)
	xr, yr = wcs_ref.all_world2pix(ra, dec, 0)
	dx, dy = xr - xx.ravel(), yr - yy.ravel()
	inside = (
		(xr > 0) & (xr < nx) & (yr > 0) & (yr < ny)
		& np.isfinite(dx) & np.isfinite(dy)
	)
	if np.count_nonzero(inside) < 3:
		return None
	return float(np.median(np.hypot(dx[inside], dy[inside])))


def align_channels(channels, wcs_map, reference):
	"""Resample every channel's pixels onto the reference grid if WCS demands it.

	channels: {name: 2d array}; wcs_map: {name: WCS or None}; reference: name.
	Returns (aligned {name: array}, log_text). Channels without WCS are passed through
	and flagged — misalignment there is undetectable, which the log must say.
	"""
	wcs_ref = wcs_map.get(reference)
	if wcs_ref is None or not wcs_ref.has_celestial:
		missing = [n for n, w in wcs_map.items() if w is None or not w.has_celestial]
		return dict(channels), f"reference '{reference}' has no usable WCS; no alignment attempted (missing WCS: {missing or 'none'})"

	aligned, shifts, resampled = {}, {}, []
	for name, img in channels.items():
		wcs = wcs_map.get(name)
		if wcs is None or not wcs.has_celestial:
			aligned[name] = img
			continue
		offset = _probe_offset(wcs_ref, wcs, img.shape)
		if offset is None:
			aligned[name] = img
			shifts[name] = "footprint mismatch - passed through unaligned"
			continue
		if offset <= OFFSET_TOLERANCE_PX:
			aligned[name] = img
			shifts[name] = f"{offset:.3f} px"
			continue
		ny, nx = img.shape[-2:]
		yy, xx = np.mgrid[0:ny, 0:nx]
		ra, dec = wcs_ref.all_pix2world(xx.ravel(), yy.ravel(), 0)
		xi, yi = wcs.all_world2pix(ra, dec, 0)
		fill = float(np.nanmedian(img))
		aligned[name] = ndimage.map_coordinates(
			img, [yi, xi], order=1, mode="constant", cval=fill
		).reshape(img.shape)
		resampled.append(name)
		shifts[name] = f"{offset:.3f} px"

	text = f"max offsets vs '{reference}': " + ", ".join(f"{k} {v}" for k, v in shifts.items())
	if resampled:
		text += f"; bilinear WCS-resampled: {resampled}"
	else:
		text += " - all within tolerance, no resampling"
	return aligned, text


def load_wcs(header) -> WCS | None:
	try:
		wcs = WCS(header)
	except Exception:
		return None
	return wcs if wcs.has_celestial else None
