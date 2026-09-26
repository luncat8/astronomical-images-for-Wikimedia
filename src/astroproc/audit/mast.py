"""MAST coverage cross-check (plan §6.3): does imaging data exist for a target list?

Input CSV: columns name,ra,dec (degrees), as written by `astroproc audit coords`. Scriptable
form of "accepts an uploaded target list, which turns this into a to-do list of objects that
have data but no picture".

Rows without coordinates are counted and skipped rather than parsed: they are the designations
no resolver knows, and a cone search cannot be built for them. A target list is one line per
object, so the skipped count has to be visible — silently dropping targets would turn a failed
resolution into an empty table that reads like "no data".
"""

import csv
from pathlib import Path


def coverage(targets, radius_deg=0.01):
	"""Observation summary per target: instrument, filters, product level counts.

	`targets` is a path or an iterable of the same rows, so a long list can be run in chunks
	without being rewritten to disk between them (experiments/live_audit.py).

	radius_deg is a cone radius, and its right size depends on the object: a 0.01 deg cone is
	fine for a galaxy, but a diffuse H II region can be a degree across, so a "no coverage"
	answer for a Sharpless object at 36" is a statement about the cone, not about the archive.
	"""
	from astropy.table import Table
	from astropy.coordinates import SkyCoord
	import astropy.units as u
	from astroquery.mast import Observations

	rows = _read_targets(targets)
	if not rows:
		raise SystemExit("no targets to check")

	summary = Table(names=("target", "n_obs", "instruments", "filters"), dtype=("U64", "i4", "U128", "U128"))
	skipped = 0
	for row in rows:
		if not row.get("ra") or not row.get("dec"):
			skipped += 1
			continue
		coord = SkyCoord(float(row["ra"]), float(row["dec"]), unit="deg", frame="icrs")
		obs = Observations.query_criteria(coordinates=coord, radius=radius_deg * u.deg, dataproduct_type="image")
		if len(obs) == 0:
			summary.add_row((row["name"], 0, "-", "-"))
			continue
		instruments = sorted(set(_texts(obs["instrument_name"])) - {"", "-"})
		filters = sorted(set(_texts(obs["filters"])) - {"", "-", "CLEAR"})
		summary.add_row((row["name"], len(obs), ",".join(instruments)[:128], ",".join(filters)[:128]))
	summary.meta["radius_deg"] = radius_deg
	summary.meta["skipped_without_coords"] = skipped
	return summary


def _texts(column):
	"""Column values as plain strings.

	MAST returns masked values for observations with no instrument or filter recorded, and a
	masked entry is neither a string nor hashable — `set(obs["instrument_name"])` raised
	TypeError: unhashable type: 'MaskedConstant' on the first live target of 2026-09-26.
	"""
	filled = column.filled("") if hasattr(column, "filled") else column
	return [str(value) for value in filled]


def _read_targets(targets):
	"""Rows from a CSV path, or the rows themselves."""
	if isinstance(targets, (str, Path)):
		return list(csv.DictReader(Path(targets).open(encoding="utf-8")))
	return list(targets)


def fetch_products(obs_id, out_dir, product_level="AUXILIARY"):
	"""Download the §6.3-preferred products for one observation id (drz/drc, cal/i2d)."""
	from astroquery.mast import Observations

	products = Observations.get_product_list(obs_id)
	wanted = Observations.filter_products(
		products, productSubGroupDescription=["DRZ", "DRC", "CAL", "I2D"]
	)
	return Observations.download_products(wanted, download_dir=str(out_dir))
