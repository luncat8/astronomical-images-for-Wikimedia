"""MAST cross-check (plan §6.3): does imaging data exist for a target list, and did it aim at it?

Input CSV: columns name,ra,dec (degrees), as written by `astroproc audit coords`. Scriptable
form of "accepts an uploaded target list, which turns this into a to-do list of objects that
have data but no picture".

`coverage` answers "is there data near here", and it answers yes for the whole sky: TESS sectors
and GALEX tiles touch every target in the 2026-09-26 Sharpless run. `pointed` is the question that
discriminates, and it is three tests in a fixed order, because the cheaper ones are false-positive
generators and the expensive one is the only verdict:

1. **Was the observation pointed?** A survey footprint is coverage, not opportunity. A name match
   on the instrument column produced six of 261 Sharpless targets, and §6.3.1 shows what became of
   them: one is illustrated under another name, two are articles with no lead image. Pointed-ness
   itself is decided by an instrument census (`observation_roles`), never by a substring.
2. **Did the footprint land on the object?** Pointing separation against the instrument footprint
   from the observation's own `s_region`, not the cone radius. `SH 2-7`'s closest HST pointing is
   3.84' from a 29" ACS/HRC field, and no amount of cone radius makes that an image of it.
3. **What does the archive call the target?** The observation's `target_name` is the name the
   proposal used, which is the name under which the object is already illustrated. `SH 2-252 F`
   is `NGC-2174`, with ten files on Commons, and neither P528 nor a cross-identification says so.

Rows without coordinates are counted and skipped rather than parsed: they are the designations no
resolver knows, and a cone search cannot be built for them. A target list is one line per object,
so the skipped count has to be visible — silently dropping targets would turn a failed resolution
into an empty table that reads like "no data".
"""

import csv
from pathlib import Path

from . import footprint

# Instrument names as MAST emits them, by role, measured with experiments/instrument_census.py
# (experiments/logs/instruments*.log). Only `imaging` can decide whether an object is imaged:
# spectroscopy has no picture to make, and an acquisition frame points at the object for 30 seconds
# and is the classic false positive. A name the archive emits and this table does not list is
# counted and reported as unknown, never folded into either group.
#
# `STIS/CCD` is the awkward one: a real 50" imaging detector, but in practice the slit-viewer finding
# chart of the visit that follows. It is filed as acquisition, so `--all-modes` is how you see it.
ROLES = {
	"HST": {
		"imaging": ("ACS", "ACS/WFC", "ACS/SBC", "WFC3/IR", "WFC3/UVIS", "WFPC2", "WFPC3",
			"NICMOS", "NICMOS/CORON"),
		"acquisition": ("STIS/CCD", "FGS", "FGS/SIRTF"),
		"spectroscopy": ("COS", "COS/FUV", "COS/NUV", "COS-STIS", "STIS", "STIS/FUV-MAMA",
			"STIS/NUV-MAMA", "ACS/GRISM"),
	},
	"JWST": {
		"imaging": ("NIRCAM/IMAGE", "NIRCAM/CORON", "MIRI/IMAGE", "MIRI/FPMIMAGE", "MIRI/CORON",
			"NIRISS/IMAGE"),
		"acquisition": ("MIRI/TARGACQ", "FGS/IMAGE"),
		"spectroscopy": ("NIRCAM/GRISM", "MIRI/MRS", "NIRISS/WFSS", "NIRISS/SOSS", "NIRSPEC",
			"NIRSPEC/IFU", "NIRSPEC/SLIT"),
	},
}
POINTED_COLLECTIONS = ("HST", "JWST")
# `observation_roles` reads this table; a name that is in none of a collection's groups is "unknown".
UNKNOWN = "unknown"
COLUMNS = ("obs_collection", "instrument_name", "filters", "obs_id", "target_name", "s_region",
	"proposal_id", "proposal_pi", "t_obs_release", "t_exptime", "dataRights")


def observation_roles(collection, instrument):
	"""`imaging`, `acquisition`, `spectroscopy` or UNKNOWN for one instrument name."""
	groups = ROLES.get(collection, {})
	return next((role for role, names in groups.items() if instrument in names), UNKNOWN)


def pointed(targets, radius_deg=0.2, imaging_only=True):
	"""One row per target: did a pointed observation image it, and what does the archive call it?

	`radius_deg` is the cone searched for candidates — wide, because a pointing that misses by
	3.84' is still the observation worth reading. `imaging_only` keeps the verdict to instruments
	that can produce an image; the excluded counts are returned as `n_other` so that a table of
	"no candidate" cannot be the result of a filter that removed everything without saying so.
	"""
	rows = read_targets(targets)
	if not rows:
		raise SystemExit("no targets to check")
	out = []
	for row in rows:
		if not row.get("ra") or not row.get("dec"):
			out.append({"target": row["name"], "verdict": "no_coordinates"})
			continue
		out.append(_pointed_row(row, radius_deg, imaging_only))
	return out


def _pointed_row(row, radius_deg, imaging_only):
	from astropy.coordinates import SkyCoord

	coord = SkyCoord(float(row["ra"]), float(row["dec"]), unit="deg", frame="icrs")
	observations = _cone(coord, radius_deg, POINTED_COLLECTIONS)
	scored = []
	other = 0
	for observation in observations:
		role = observation_roles(observation["collection"], observation["instrument"])
		if role == UNKNOWN or (imaging_only and role != "imaging"):
			other += 1
			continue
		separation = footprint.distance_arcsec(observation["region"], coord)
		scored.append((separation if separation is not None else float("inf"), observation, separation))
	closest = min(scored, key=lambda entry: entry[0], default=None)
	# the resolver's object type travels with the target: §6.2.1 measured it as the free
	# false-positive detector (250 HII, then two planetary nebulae, a bubble and two stars)
	result = {"target": row["name"], "otype": row.get("otype", ""),
		"n_pointed": len(scored), "n_other": other}
	if closest is None:
		return {**result, "verdict": "no_pointed_data"}
	_, observation, separation = closest
	result.update({
		# `min` sorts None last via inf, so the closest row can still have an unreadable footprint.
		"archive_name": observation["target_name"],
		"obs_id": observation["obs_id"],
		"instrument": observation["instrument"],
		"filters": observation["filters"],
		"fov_arcsec": _fov(observation["region"]),
		"sep_arcsec": None if separation is None else round(separation, 1),
		"n_covering": sum(1 for entry in scored if entry[2] == 0.0),
		"proposal": observation["proposal"],
		"pi": observation["pi"],
		"public": observation["public"],
		"rights": observation["rights"],
	})
	result["verdict"] = _verdict(result["n_covering"], closest[2])
	return result


def _verdict(n_covering, separation):
	"""The four outcomes, kept apart: a target whose closest footprint could not be read is not a
	target that was missed, and printing either verdict for it would be a statement the archive never
	made."""
	if n_covering:
		return "imaged"
	return "footprint_unreadable" if separation is None else "footprint_missed"


def _fov(region):
	bounds = footprint.bounds_arcsec(region)
	return "-" if bounds is None else f"{bounds[0]:.0f}x{bounds[1]:.0f}"


def _cone(coord, radius_deg, collections):
	"""Observation rows for a cone search, as plain dicts.

	Dict rows rather than an astropy Table: the geometry, the role table and the row assembly are
	then testable without the network, and the output is already the CSV shape the rest of the
	chain passes around.
	"""
	from astroquery.mast import Observations
	import astropy.units as u

	rows = Observations.query_criteria(coordinates=coord, radius=radius_deg * u.deg,
		obs_collection=list(collections), dataproduct_type="image")
	# each column is read once: a cone search returns thousands of rows, and materialising a column
	# per field per row is the difference between one pass and a quadratic one. A column the archive
	# does not publish becomes empty rather than a KeyError: the release date and the exposure time
	# are convenience, and neither is worth losing a whole cone search to.
	columns = {name: _column(rows[name]) if name in rows.colnames else [""] * len(rows) for name in COLUMNS}
	public = _date_cache(columns["t_obs_release"])
	return [{
		"collection": columns["obs_collection"][index],
		"instrument": columns["instrument_name"][index],
		"filters": columns["filters"][index],
		"obs_id": columns["obs_id"][index],
		"target_name": columns["target_name"][index],
		"region": columns["s_region"][index],
		"proposal": columns["proposal_id"][index],
		"pi": columns["proposal_pi"][index],
		"public": public[columns["t_obs_release"][index]],
		"exptime": columns["t_exptime"][index],
		"rights": columns["dataRights"][index],
	} for index in range(len(rows))]


def _column(column):
	"""A column as plain strings.

	MAST masks what it does not know, and a masked value is neither a string nor hashable —
	`set(obs["instrument_name"])` raised `TypeError: unhashable type: 'MaskedConstant'` on the first
	live target of 2026-09-26, so every column goes through here.
	"""
	filled = column.filled("") if hasattr(column, "filled") else column
	return [str(value) for value in filled]


def _date_cache(values):
	"""{MJD string: ISO date} for the distinct release dates — the proprietary-period end, and the
	timeliness axis of §6.4. One conversion per date rather than per row: a program makes hundreds of
	exposures that all go public on the same day."""
	from astropy.time import Time

	dates = {}
	for value in set(values):
		dates[value] = "" if not value or value in ("--", "nan") else Time(float(value), format="mjd").isot[:10]
	return dates


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

	rows = read_targets(targets)
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
		instruments = sorted(set(_column(obs["instrument_name"])) - {"", "-"})
		filters = sorted(set(_column(obs["filters"])) - {"", "-", "CLEAR"})
		summary.add_row((row["name"], len(obs), ",".join(instruments)[:128], ",".join(filters)[:128]))
	summary.meta["radius_deg"] = radius_deg
	summary.meta["skipped_without_coords"] = skipped
	return summary


def write_pointed(rows, path):
	"""The pointed rows as CSV — the file `audit commons` and the rubric read next."""
	fields = ("target", "otype", "archive_name", "verdict", "n_pointed", "n_covering", "n_other",
		"sep_arcsec", "obs_id", "instrument", "filters", "fov_arcsec", "proposal", "pi", "public",
		"rights")
	with Path(path).open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
		writer.writeheader()
		writer.writerows(rows)
	return path


def read_targets(targets):
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
