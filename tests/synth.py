"""Synthetic FITS scenes with known ground truth (stars, colours, skies, WCS).

Used by tests and the demo run: if the pipeline is colour-correct, the recovered
star colours match the planted ones and the audit trail is complete.
"""

from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

# intrinsic (R, G, B) flux ratios per star class — the ground truth colour test
STAR_COLOURS = {
	"blue": (0.65, 0.85, 1.30),
	"white": (1.00, 1.00, 1.00),
	"red": (1.45, 1.10, 0.70),
}

SKY_LEVELS = {"Halpha": 120.0, "OIII": 90.0, "SII": 105.0}
THROUGHPUT = {"Halpha": 1.0, "OIII": 0.8, "SII": 0.9}
SAT_LIMIT = 60000.0


def make_wcs(shape, ra0=150.1, dec0=2.2, mirror=False, rotation_deg=0.0):
	w = WCS(naxis=2)
	w.wcs.crpix = [(shape[1] + 1) / 2, (shape[0] + 1) / 2]
	# mirror flips exactly one axis (a two-axis flip is a 180 deg rotation, not a mirror)
	w.wcs.cdelt = np.array([0.0001 if mirror else -0.0001, 0.0001])
	w.wcs.crval = [ra0, dec0]
	w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
	if rotation_deg:
		r = np.deg2rad(rotation_deg)
		w.wcs.pc = [[np.cos(r), np.sin(r)], [-np.sin(r), np.cos(r)]]
	w.wcs.equinox = 2000.0
	return w


def make_scene(shape=(384, 512), seed=42, n_stars=48, saturate_one_star=True):
	"""Returns (channels dict, truth dict). Channel fluxes: star_col * flux * throughput."""
	rng = np.random.default_rng(seed)
	channels = {
		name: rng.normal(sky, 4.0, shape).astype(np.float32)
		for name, sky in SKY_LEVELS.items()
	}
	truth = {"stars": [], "colours": []}

	for _ in range(n_stars):
		y = rng.integers(6, shape[0] - 6)
		x = rng.integers(6, shape[1] - 6)
		flux = 10 ** rng.uniform(2.3, 4.6)
		colour = STAR_COLOURS[rng.choice(list(STAR_COLOURS))]
		truth["stars"].append((y, x, flux))
		truth["colours"].append(colour)
		for i, name in enumerate(channels):
			_add_star(channels[name], y, x, flux * colour[i] * THROUGHPUT[name], saturate_one_star and i == 0 and flux > 3e4)

	# one extended source (galaxy-ish) with its own intrinsic colour
	yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
	galaxy = 900.0 * np.exp(-(((xx - shape[1] * 0.62) ** 2) / (2 * 28.0 ** 2) + ((yy - shape[0] * 0.4) ** 2) / (2 * 17.0 ** 2)))
	truth["galaxy_colour"] = (1.25, 1.0, 0.75)
	for i, name in enumerate(channels):
		channels[name] += (galaxy * truth["galaxy_colour"][i] * THROUGHPUT[name]).astype(np.float32)

	truth["wcs"] = make_wcs(shape)
	return channels, truth


def _add_star(img, y, x, peak, saturate=False):
	if saturate:
		peak = SAT_LIMIT * 1.01
	rr, cc = np.mgrid[-3:4, -3:4]
	kernel = np.exp(-(rr ** 2 + cc ** 2) / (2 * 1.1 ** 2))
	slice_img = img[y - 3:y + 4, x - 3:x + 4]
	slice_img += (kernel * peak).astype(np.float32)
	if saturate:
		np.clip(slice_img, None, SAT_LIMIT * 1.01, out=slice_img)


def write_channels(channels, out_dir, mirror=False, rotation_deg=0.0, object_name="SYNTH1"):
	"""Write per-channel FITS with provenance-style headers + WCS; returns paths dict."""
	out_dir = Path(out_dir)
	out_dir.mkdir(parents=True, exist_ok=True)
	paths = {}
	for name, data in channels.items():
		w = make_wcs(data.shape, mirror=mirror, rotation_deg=rotation_deg)
		header = w.to_header()
		header["OBJECT"] = object_name
		header["FILTER"] = name
		header["INSTRUME"] = "SYNTH-CAM"
		header["TELESCOP"] = "SYNTH-SCOPE"
		header["EXPTIME"] = 1200.0
		header["DATE-OBS"] = "2026-01-15T03:24:00"
		header["SATURATE"] = SAT_LIMIT
		path = out_dir / f"{object_name}_{name}.fits"
		fits.PrimaryHDU(data, header).writeto(path, overwrite=True)
		paths[name] = path
	return paths


from pathlib import Path  # noqa: E402  (used above via deferred import for tidy call order)
