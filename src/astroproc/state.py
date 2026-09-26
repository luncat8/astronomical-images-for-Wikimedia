"""Data-state inspection (plan §7.1): linear vs already-stretched, saturation, product hints.

The histogram is the tell: linear data has a narrow sky-background peak with a long faint
tail; stretched data has a flatter, wider distribution. We measure both pieces of evidence
and report them so a reviewer can check the verdict, not just take it.

The histogram only carries that argument when the frame contains exposed sky. A nebula that
fills the field has no sky peak, its median sits inside the object's own light, and
median/span reads high — measured live on the first real data this code saw (2026-09-26), a
linear WFC3/IR drizzle of NGC 2174, a 0.25 median/span against a 0.02 threshold, and the
verdict "stretched" on data the plan itself recommends. So a product that declares a physical
unit *and* standard pipeline provenance is linear by construction, the header outranks the
histogram, and the disagreement is written into the report rather than hidden.
"""

from dataclasses import dataclass, field

import numpy as np
from astropy.stats import sigma_clipped_stats
from astropy.io import fits

# sigma-clipped median as a fraction of the p0.1..p99.9 span: deep linear data sits
# at <0.6%, processed preview products land at 10%+. Between the two: ambiguous.
STRETCHED_MEDIAN_FRACTION = 0.02
AMBIGUOUS_MEDIAN_FRACTION = 0.005
# fraction of pixels allowed outside the sky core of linear data (reported, not decisive)
CORE_FRACTION_THRESHOLD = 0.97

# Only reduced pipeline products carry these; a hand-made preview or a screen grab does not.
PIPELINE_KEYS = ("NCOMBINE", "DRIZCORR", "CAL_VER", "MDRIZSKY", "PFLTFILE", "OPUS_VER")
# A physical unit means the numbers mean something; "DN" alone does not, it is also a stretched
# 8-bit preview's unit.
PHYSICAL_UNITS = ("ELECTRON", "E-", "COUNT RATE", "JY", "JYS", "PHOTON", "WATT", "CT RATE")

PROVENANCE_KEYS = (
	"FILTER", "FILTER1", "FILTER2", "DATE-OBS", "EXPTIME", "TEXPTIME",
	"INSTRUME", "TELESCOP", "OBS_ID", "OBSID", "PROGID", "PROPOSID",
	"TARGNAME", "SATURATE", "BUNIT", "NCOMBINE", "CSSRELEASED", "PGRIDNAME",
)


@dataclass
class StateReport:
	path: str = ""
	shape: tuple = ()
	dtype: str = ""
	sky: float = 0.0
	sky_std: float = 0.0
	core_fraction: float = 1.0
	invalid_fraction: float = 0.0
	median_fraction: float = 0.0
	verdict: str = "unknown"
	saturated_count: int = 0
	sat_limit: float | None = None
	notes: list = field(default_factory=list)
	provenance: dict = field(default_factory=dict)

	def summary(self) -> str:
		lines = [
			f"file:            {self.path}",
			f"shape/dtype:     {self.shape} {self.dtype}",
			f"sky (clipped):   {self.sky:.6g} +/- {self.sky_std:.3g}",
			f"core fraction:   {self.core_fraction:.4f}  (reference {CORE_FRACTION_THRESHOLD})",
			f"invalid pixels:  {self.invalid_fraction:.4%} non-finite (excluded from every number below)",
			f"median/span:     {self.median_fraction:.3g}  "
			f"(stretched > {STRETCHED_MEDIAN_FRACTION:g}, ambiguous > {AMBIGUOUS_MEDIAN_FRACTION:g})",
			f"verdict:         {self.verdict}",
		]
		if self.sat_limit is not None:
			lines.append(f"saturated px:    {self.saturated_count} (limit {self.sat_limit:g})")
		for note in self.notes:
			lines.append(f"note:            {note}")
		for key in PROVENANCE_KEYS:
			if key in self.provenance:
				lines.append(f"{key.lower()+':':<17}{self.provenance[key]}")
		return "\n".join(lines)


def sky_stats(img, sigma=3.0, maxiters=10):
	"""Sigma-clipped (median, std) — the standard sky/background estimator."""
	_, median, std = sigma_clipped_stats(img, sigma=sigma, maxiters=maxiters)
	return float(median), float(std)


def header_says_linear(header) -> bool:
	"""Does the header declare a physical unit *and* standard pipeline provenance?"""
	if not header:
		return False
	unit = str(header.get("BUNIT", "")).upper()
	return any(u in unit for u in PHYSICAL_UNITS) and any(key in header for key in PIPELINE_KEYS)


def classify(img, sat_limit=None, header=None) -> StateReport:
	img = np.asarray(img)
	report = StateReport(shape=img.shape, dtype=str(img.dtype))

	# Non-finite pixels are blank coverage, not data. Every product that dithers or mosaics
	# writes them — the first real WFC3/IR drz files measured here (2026-09-26) have them, and
	# numpy's percentiles do not skip them: `np.percentile` returned NaN, the span became NaN,
	# and `nan > 0.02` is False, so a stretched product would have been labelled linear.
	finite = np.isfinite(img)
	pixels = img[finite]
	report.invalid_fraction = 1.0 - pixels.size / img.size
	med, std = sky_stats(pixels)
	report.sky, report.sky_std = med, std

	bright = float(np.percentile(pixels, 99.9))
	low = float(np.percentile(pixels, 0.1))
	span = max(bright - low, np.finfo(np.float64).tiny)
	inside = np.count_nonzero((pixels > med - 3.0 * std) & (pixels < med + 5.0 * std))
	report.core_fraction = inside / pixels.size
	# the decision metric: how far the background sits above the bottom of the data span.
	# Robust against star tails because both ends are percentile-anchored.
	report.median_fraction = (med - low) / span

	if header_says_linear(header) and report.median_fraction > STRETCHED_MEDIAN_FRACTION:
		report.verdict = "linear"
		report.notes.append(
			f"median/span {report.median_fraction:.3g} would read stretched, but the product "
			f"declares {header.get('BUNIT')} and pipeline provenance"
			f"{', ' + header['INSTRUME'] if 'INSTRUME' in header else ''}: linear by construction. "
			"The histogram argument needs exposed sky, and a subject that fills the frame has none"
		)
	elif report.median_fraction > STRETCHED_MEDIAN_FRACTION:
		report.verdict = "stretched"
		report.notes.append(
			"already-stretched data must be linearised before compositing (plan §7.1); "
			"automatic inversion is not attempted - provide linear products (JWST cal/i2d, "
			"HST drz/drc) or an explicit inverse-stretch function"
		)
	else:
		report.verdict = "linear"
		if report.median_fraction > AMBIGUOUS_MEDIAN_FRACTION:
			report.notes.append(
				"background noticeably above the bottom of the span - check the product is "
				"linear before trusting inter-channel ratios"
			)

	if report.invalid_fraction > 0:
		report.notes.append(
			"non-finite pixels excluded from every statistic — blank coverage, not zero signal"
		)
	if sat_limit is not None:
		report.sat_limit = float(sat_limit)
		report.saturated_count = int(np.count_nonzero(pixels >= sat_limit))
	return report


def load_image(path):
	"""Largest 2D image HDU of a FITS file -> (data, header)."""
	with fits.open(path) as hdus:
		hdu = max(
			(h for h in hdus if h.data is not None and hasattr(h.data, "ndim") and h.data.ndim >= 2),
			key=lambda h: h.data.size,
		)
		return np.asarray(hdu.data), hdu.header.copy()


def header_provenance(header) -> dict:
	return {key: str(header[key]) for key in PROVENANCE_KEYS if key in header}


def has_wcs_keys(header) -> bool:
	return any(key.startswith(("CTYPE", "CD1_", "PC1_")) for key in header)


def inspect_file(path, sat_limit=None, hdu_index=None) -> StateReport:
	with fits.open(path) as hdus:
		if hdu_index is not None:
			hdu = hdus[hdu_index]
		else:
			hdu = max(
				(h for h in hdus if h.data is not None and hasattr(h.data, "ndim") and h.data.ndim >= 2),
				key=lambda h: h.data.size,
			)
		report = classify(np.asarray(hdu.data), sat_limit=sat_limit, header=hdu.header)
		report.path = str(path)
		header = hdu.header
		report.provenance = header_provenance(header)
		if "SATURATE" in header and sat_limit is None:
			report.sat_limit = float(header["SATURATE"])
			report.saturated_count = int(np.count_nonzero(hdu.data >= report.sat_limit))
		for hint in ("DRZ", "DRC", "I2D", "MOSAIC", "COMB"):
			if any(hint in key for key in header):
				report.notes.append(f"header contains '{hint}' - possibly combined/composited product")
		if hdu.data.ndim >= 3:
			report.notes.append("3+ dimensional data - check whether this is an RGB/ cube product")
		if not has_wcs_keys(header):
			report.notes.append("no WCS - orientation check (plan §7.6) needs an external reference")
	return report
