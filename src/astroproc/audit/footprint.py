"""Where an observation actually looked, from the archive's own geometry (plan §6.3).

A cone search answers "is there an observation within N degrees", which is coverage, not
opportunity. The question that decides a candidate is whether the instrument's *footprint* fell on
the object: on 2026-09-26 the closest HST pointing to `SH 2-7` was 3.84' away from a 29" ACS/HRC
field, i.e. eight fields off, and the object is imaged by nothing. MAST publishes that footprint in
the observation's own `s_region` column, as a POLYGON (HST and JWST imaging) or a CIRCLE (COS), so
the test needs no footprint table of its own and cannot drift from the instrument it describes.

Geometry runs in a tangent plane with a single cos(lat) factor. For a field of a few arcminutes the
error is under a milliarcsecond, far below the point of the test.
"""

import math

import numpy as np
from astropy.coordinates import SkyCoord

UNREADABLE = None


def parse(region):
	"""(kind, geometry) for one `s_region` value, or (None, None) when it is not a footprint.

	`geometry` is an (n, 2) array of (ra, dec) degrees for POLYGON, and (centre, radius_deg) for
	CIRCLE. Unreadable values have to reach the caller as such: an unparseable footprint is not a
	target that failed the test, and the two must not print the same.
	"""
	text = str(region).strip()
	if not text or text == "--":
		return None, None
	head, _, rest = text.partition(" ")
	kind = head.upper()
	try:
		values = [float(value) for value in rest.replace(",", " ").split()]
	except ValueError:
		return None, None
	if kind == "POLYGON" and len(values) >= 6 and len(values) % 2 == 0:
		return "POLYGON", np.array(values).reshape(-1, 2)
	if kind in ("CIRCLE", "RADIUS") and len(values) == 3:
		return "CIRCLE", (np.array(values[:2]), values[2])
	return None, None


def distance_arcsec(region, coord):
	"""Arcseconds from `coord` to the nearest point of the footprint; 0.0 when it is inside."""
	kind, geometry = parse(region)
	if kind is None:
		return UNREADABLE
	if kind == "CIRCLE":
		centre, radius = geometry
		return max(0.0, coord.separation(SkyCoord(*centre, unit="deg", frame="icrs")).deg - radius) * 3600.0
	centre = geometry.mean(axis=0)
	flat = _project(geometry, centre)
	lon, lat = coord.spherical.lon.deg, coord.spherical.lat.deg
	point = _project([(lon, lat)], centre)[0]
	if _contains(flat, point):
		return 0.0
	edges = (_segment_distance(point, flat[i], flat[(i + 1) % len(flat)]) for i in range(len(flat)))
	return min(edges) * 3600.0


def bounds_arcsec(region):
	"""(width, height) of the footprint bounding box in arcseconds — the §13.1 "FOV" field.

	Diagonal size would read as a field size and is not one: a 2.3 x 2.3' WFC3/IR frame is 3.3'
	corner to corner, and reporting that invites a reviewer to expect a field that is not there.
	"""
	kind, geometry = parse(region)
	if kind is None:
		return None
	if kind == "CIRCLE":
		diameter = geometry[1] * 7200.0
		return (diameter, diameter)
	flat = _project(geometry, geometry.mean(axis=0))
	span = (flat.max(axis=0) - flat.min(axis=0)) * 3600.0
	return (float(span[0]), float(span[1]))


def _project(points, centre):
	"""Equatorial degrees to tangent-plane degrees about `centre`: a flat times cos(lat), nothing else."""
	points = np.atleast_2d(np.asarray(points, dtype=float))
	cos_lat = math.cos(math.radians(centre[1]))
	return np.column_stack([(points[:, 0] - centre[0]) * cos_lat, points[:, 1] - centre[1]])


def _contains(flat, point):
	"""Crossing-number test for a point inside a polygon."""
	inside = False
	x, y = point
	previous = flat[-1]
	for vertex in flat:
		if (vertex[1] > y) != (previous[1] > y):
			edge_x = (previous[0] - vertex[0]) * (y - vertex[1]) / (previous[1] - vertex[1]) + vertex[0]
			if x < edge_x:
				inside = not inside
		previous = vertex
	return inside


def _segment_distance(point, start, end):
	"""Distance from a point to a segment — the boundary case of `_contains` returning False."""
	edge = end - start
	length = float(edge @ edge)
	if length == 0.0:
		return float(np.hypot(*(point - start)))
	fraction = min(1.0, max(0.0, float((point - start) @ edge) / length))
	return float(np.hypot(*(point - (start + fraction * edge))))
