"""MAST coverage cross-check (plan §6.3): does imaging data exist for a target list?

Input CSV: columns name,ra,dec (degrees). Scriptable form of "accepts an uploaded
target list, which turns this into a to-do list of objects that have data but no picture".
"""

import csv
from pathlib import Path


def coverage(targets_csv, radius_deg=0.01, compact=True):
	"""Observation summary per target: instrument, filters, product level counts."""
	from astropy.table import Table
	from astropy.coordinates import SkyCoord
	import astropy.units as u
	from astroquery.mast import Observations

	rows = list(csv.DictReader(Path(targets_csv).open(encoding="utf-8")))
	if not rows:
		raise SystemExit(f"no targets in {targets_csv}")

	summary = Table(names=("target", "n_obs", "instruments", "filters"), dtype=("U64", "i4", "U128", "U128"))
	for row in rows:
		coord = SkyCoord(float(row["ra"]), float(row["dec"]), unit="deg", frame="icrs")
		obs = Observations.query_criteria(coordinates=coord, radius=radius_deg * u.deg, dataproduct_type="image")
		if len(obs) == 0:
			summary.add_row((row["name"], 0, "-", "-"))
			continue
		instruments = sorted(set(obs["instrument_name"]))
		filters = sorted({f for f in obs["filters"] if f and f != "CLEAR"})
		summary.add_row((row["name"], len(obs), ",".join(instruments)[:128], ",".join(filters)[:128]))
	return summary


def fetch_products(obs_id, out_dir, product_level="AUXILIARY"):
	"""Download the §6.3-preferred products for one observation id (drz/drc, cal/i2d)."""
	from astroquery.mast import Observations

	products = Observations.get_product_list(obs_id)
	wanted = Observations.filter_products(
		products, productSubGroupDescription=["DRZ", "DRC", "CAL", "I2D"]
	)
	return Observations.download_products(wanted, download_dir=str(out_dir))
