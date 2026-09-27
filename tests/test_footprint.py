import math

import pytest
from astropy.coordinates import SkyCoord

from astroproc.audit import footprint

# The real WFC3/IR footprint of ichx02020, the visit that images NGC 2174 (fetched 2026-09-26).
# It is a rotated square with 25 vertices, so it is what the parser and the bounds are checked
# against; the geometry laws use a clean synthetic box, where the answer is known exactly.
WFC3IR = ("POLYGON 92.30540717 20.50816356 92.27214434 20.48621694 92.29315482 20.45845444 "
	"92.293154850196757 20.458454459927445 92.29438936 20.45682283 92.32764894 20.47876515 "
	"92.326414595910364 20.480397030921058 92.32641464 20.48039706 92.30540717 20.50816356 "
	"92.30540717 20.50816356")
POINTING = SkyCoord(92.29930679, 20.48330624, unit="deg", frame="icrs")
# A 100 x 100 arcsecond box centred at (100, 20.5). The RA half-width is divided by cos(dec), so the
# box is 100" wide on the sky and not 106.7" — which is exactly the mistake the cosine test catches.
BOX_AT_20 = ("POLYGON 99.985175 20.513889 100.014825 20.513889 100.014825 20.486111 "
	"99.985175 20.486111 99.985175 20.513889")


def north(coord, arcsec):
	"""The point `arcsec` due north along the meridian — exact, and not a great-circle guess."""
	return SkyCoord(coord.ra.deg, coord.dec.deg + arcsec / 3600, unit="deg", frame="icrs")


def east(coord, arcsec):
	"""The point `arcsec` due east — a true angular distance, so the RA offset carries a cos(dec)."""
	return SkyCoord(coord.ra.deg + arcsec / 3600 / math.cos(math.radians(coord.dec.deg)),
		coord.dec.deg, unit="deg", frame="icrs")


def test_parse_reads_polygon_and_circle():
	kind, geometry = footprint.parse(WFC3IR)
	assert kind == "POLYGON" and geometry.shape == (10, 2)
	kind, (centre, radius) = footprint.parse("CIRCLE 16.12127447 2.1240249 0.00034722")
	assert kind == "CIRCLE" and list(centre) == [16.12127447, 2.1240249] and radius == 0.00034722


def test_parse_refuses_what_it_cannot_read():
	for value in ["--", "", "M4 0.1 0.2", "POLYGON 1 2 3", "POLYGON not-a-number", "CIRCLE 1 2"]:
		assert footprint.parse(value) == (None, None)
		assert footprint.distance_arcsec(value, POINTING) is None
		assert footprint.bounds_arcsec(value) is None


def test_pointing_and_the_measured_offset_are_inside_their_own_footprint():
	assert footprint.distance_arcsec(WFC3IR, POINTING) == 0.0
	# SH 2-252 F sits 0.74' from this pointing, and this is the project's own dataset
	assert footprint.distance_arcsec(WFC3IR, north(POINTING, 44)) == 0.0


def test_distance_is_the_gap_to_the_nearest_edge():
	"""Past a corner, the nearest point of a convex footprint is a vertex; past an edge, it is the foot
	of the perpendicular. The rotated WFC3/IR field gives one of each, and the numbers are its own."""
	corner = SkyCoord(92.30540717, 20.50816356, unit="deg", frame="icrs")
	assert footprint.distance_arcsec(WFC3IR, north(corner, 60)) == pytest.approx(60, abs=0.5)
	assert footprint.distance_arcsec(WFC3IR, north(corner, 240)) == pytest.approx(240, abs=1.0)
	# 60" due east of the topmost vertex crosses the edge that runs down-right and lands 49.0" from it
	assert footprint.distance_arcsec(WFC3IR, east(corner, 60)) == pytest.approx(49.0, abs=0.2)


def test_footprint_bounds_are_not_the_diagonal():
	width, height = footprint.bounds_arcsec(WFC3IR)
	assert (width, height) == pytest.approx((187.2, 184.8), abs=0.5)
	corner = SkyCoord(92.30540717, 20.50816356, unit="deg", frame="icrs")
	diagonal = corner.separation(SkyCoord(92.27214434, 20.45682283, unit="deg", frame="icrs")).arcsec
	assert diagonal > max(width, height), "a corner-to-corner size would overstate the field"


def test_cosine_of_latitude_is_applied():
	"""A tangent plane without cos(dec) is 6.7% too wide in RA at 20 degrees, and this catches it."""
	centre = SkyCoord(100, 20.5, unit="deg", frame="icrs")
	assert footprint.distance_arcsec(BOX_AT_20, centre) == 0.0
	assert footprint.distance_arcsec(BOX_AT_20, north(centre, 200)) == pytest.approx(150, abs=0.5)
	assert footprint.distance_arcsec(BOX_AT_20, east(centre, 200)) == pytest.approx(150, abs=0.5)
	assert footprint.bounds_arcsec(BOX_AT_20) == pytest.approx((100, 100), abs=1.0)


def test_circular_footprint():
	region = "CIRCLE 16.12127447 2.1240249 0.00034722"  # 1.25 arcsec radius
	centre = SkyCoord(16.12127447, 2.1240249, unit="deg", frame="icrs")
	assert footprint.distance_arcsec(region, centre) == 0.0
	assert footprint.distance_arcsec(region, north(centre, 2.75)) == pytest.approx(1.5, abs=0.01)
	assert footprint.distance_arcsec(region, north(centre, 3.5)) == pytest.approx(2.25, abs=0.01)
	assert footprint.bounds_arcsec(region) == pytest.approx((2.5, 2.5), abs=0.001)
