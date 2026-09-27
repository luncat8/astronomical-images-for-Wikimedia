"""Multi-filter imaging sets that are pointed, covering and newly public (plan §6.3, §6.4).

`audit pointed` answers "is this object imaged" from the catalogue side, and the 2026-09-26
Sharpless run is what that axis looks like when it is nearly exhausted: 261 resoluble gaps, six with
a pointed HST/JWST observation, and a Commons check that then removed or reframed most of those
(§6.3.1). This module asks the question from the other end, which §6.3 calls the most scalable and
most overlooked one: which objects carry a *recently public, multi-filter* pointed dataset, i.e.
exactly what a colour composite needs and what the archive has never rendered?

Three tests, in the order §6.3 fixes, and the fourth that is this module's reason to exist:

1. pointed imaging, not a survey footprint and not an acquisition frame (`mast.observation_roles`,
   measured instrument census);
2. the footprint covering the object's coordinates, not merely within a cone radius
   (`footprint.distance_arcsec`, from the observation's own `s_region`);
3. enough filters to make colour — a set of one is a grayscale image, and two narrowbands are the
   documented minimum;
4. public, and recently: the proprietary period ends and nobody renders the data (`--since`).

A **set** is one program's pointing with one detector — `(collection, instrument, proposal)`. A
program is the unit that chose a coherent filter set, so its filters are the ones that were meant to
be compared; merging a decade of observations into a list of wavelengths nothing observed together
invents a composite the archive cannot support. Mixing detectors across a set is the §7.4 alignment
problem, not a filter change, and it is left where it belongs: with the operator, who can see both
sets in the output.

The release date of a set is its *last* exposure's, because that is when the set became usable.
A set whose rows carry no release date is kept and its date left empty — "unknown" is not "old", and
folding the two together would hide data behind a filter that claims to be about dates.
"""

import csv
from pathlib import Path

from . import footprint, mast

SET_COLUMNS = (
	"target", "otype", "verdict", "archive_name", "collection", "instrument", "proposal", "pi", "filters",
	"n_filters", "n_exposures", "n_covering", "n_other", "exptime_s", "public", "fov_arcsec",
	"obs_id", "rights",
)
# The verdicts that are an answer, kept beside the ones that are not: a table of "no set" has to be
# readable as "checked, and there is none", not as a filter that removed everything.
COLOUR_SET = "colour_set"
NO_COORDINATES = "no_coordinates"
NO_POINTED_DATA = "no_pointed_data"
MISSED = "footprint_missed"
UNREADABLE = "footprint_unreadable"
OLD_RELEASE = "released_before_window"
TOO_FEW_FILTERS = "fewer_filters_than_requested"


def colour_sets(targets, radius_deg=0.2, since="", min_filters=3, imaging_only=True):
	"""One row per target, plus one row per qualifying set: what could be composited, and how new.

	`targets` is a path or the rows of the `name,ra,dec` CSV `audit coords` writes. `radius_deg` is
	the cone searched for candidates and is deliberately wide: a pointing 3.84' off a 29" field is
	the observation worth reading, and the footprint test is what decides. `since` is an ISO date;
	sets released before it come back with verdict `released_before_window` instead of disappearing.
	"""
	rows = mast.read_targets(targets)
	if not rows:
		raise SystemExit("no targets to check")
	out = []
	for row in rows:
		if not row.get("ra") or not row.get("dec"):
			out.append({"target": row["name"], "verdict": NO_COORDINATES})
			continue
		out.extend(_target_sets(row, radius_deg, since, min_filters, imaging_only))
	return out


def _target_sets(row, radius_deg, since, min_filters, imaging_only):
	from astropy.coordinates import SkyCoord

	coord = SkyCoord(float(row["ra"]), float(row["dec"]), unit="deg", frame="icrs")
	observations = mast._cone(coord, radius_deg, mast.POINTED_COLLECTIONS)
	groups, counts = _covering_groups(observations, coord, imaging_only)
	base = {"target": row["name"], "otype": row.get("otype", ""), "n_other": counts["other"],
		"n_covering": sum(len(rows) for rows in groups.values())}
	if not groups:
		return [{**base, "verdict": _empty_verdict(counts)}]
	return [dict(base, **set_row) for set_row in _ranked_sets(groups, since, min_filters)]


def _empty_verdict(counts):
	"""Why there is no set, with the four reasons kept apart.

	"Nothing aimed at this object" and "something aimed at it and missed" are different answers, and
	so is "the archive did not let the test decide" — each sends the operator somewhere else. Only
	`no_pointed_data` says there is nothing to look at here at all.
	"""
	if counts["unreadable"]:
		return UNREADABLE
	return NO_POINTED_DATA if not counts["pointed"] else MISSED


def _covering_groups(observations, coord, imaging_only):
	"""Covering pointed observations grouped into detector/program sets, plus the excluded counts.

	An observation whose footprint cannot be read is counted, never dropped: it is a row the archive
	does not let the test decide, and it is the difference between "no data" and "not checked".
	"""
	groups, counts = {}, {"other": 0, "unreadable": 0, "pointed": 0}
	for observation in observations:
		role = mast.observation_roles(observation["collection"], observation["instrument"])
		if role == mast.UNKNOWN or (imaging_only and role != "imaging"):
			counts["other"] += 1
			continue
		counts["pointed"] += 1
		separation = footprint.distance_arcsec(observation["region"], coord)
		if separation is None:
			counts["unreadable"] += 1
			continue
		if separation > 0.0:
			continue
		groups.setdefault(_set_key(observation), []).append(observation)
	return groups, counts


def _set_key(observation):
	"""One program's pointing with one detector, plus the archive's name for the target: the name is
	in the key because a proposal that observed two objects produced two sets, not one."""
	return (observation["collection"], observation["instrument"], observation["proposal"],
		observation["target_name"])


def _ranked_sets(groups, since, min_filters):
	"""Set rows for one target, most recently public first and then the most filters — the §6.4
	timeliness axis, and the reason the ordering is not alphabetical."""
	sets = [_set_row(key, observations) for key, observations in groups.items()]
	sets.sort(key=lambda row: (row["public"], row["n_filters"]), reverse=True)
	for row in sets:
		row["verdict"] = _verdict(row, since, min_filters)
	return sets


def _set_row(key, observations):
	collection, instrument, proposal, target_name = key
	releases = [observation["public"] for observation in observations if observation["public"]]
	exposures = [value for value in (_number(observation.get("exptime")) for observation in observations) if value]
	# the frame of the deepest exposure: in a table where a 29" ACS/HRC field and a 187" WFC3/IR one
	# are both "a filter set", the frame is what says whether the object fits in it
	deepest = max(observations, key=lambda observation: _number(observation.get("exptime")))
	filters = _filters(observations)
	return {
		"archive_name": target_name,
		"collection": collection,
		"instrument": instrument,
		"proposal": proposal,
		"pi": observations[0]["pi"],
		"filters": ";".join(filters),
		"n_filters": len(filters),
		"n_exposures": len(observations),
		"exptime_s": max(exposures) if exposures else "",
		"fov_arcsec": _size(footprint.bounds_arcsec(deepest["region"])),
		"public": max(releases) if releases else "",
		"obs_id": observations[0]["obs_id"],
		"rights": observations[0]["rights"],
	}


def _filters(observations):
	"""Distinct filters of a set: one MAST row per exposure, and a cell can hold several."""
	names = {name.strip() for observation in observations
		for name in str(observation.get("filters", "")).replace(",", ";").split(";")}
	return sorted(names - {"", "--", "CLEAR", "NONE"})


def _size(bounds):
	return "-" if bounds is None else f"{bounds[0]:.0f}x{bounds[1]:.0f}"


def _verdict(row, since, min_filters):
	# the window first, because it is the axis this module exists for, and an empty release date is
	# "unknown", not "old": §7.1's rule about missing evidence applies to a date as much as a header
	if since and row["public"] and row["public"] < since:
		return OLD_RELEASE
	return TOO_FEW_FILTERS if row["n_filters"] < min_filters else COLOUR_SET


def _number(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def write_sets(rows, path):
	"""All rows, verdicts included — the CSV `audit commons` filters to the answers and `audit score`
	reads the survivors from."""
	with Path(path).open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=list(SET_COLUMNS), extrasaction="ignore")
		writer.writeheader()
		writer.writerows(rows)
	return path
