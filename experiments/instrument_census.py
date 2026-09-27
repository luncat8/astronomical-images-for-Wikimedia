"""What instrument names does MAST actually use? Census a window, do not guess (measured 2026-09-26).

`audit pointed` decides which observation "aimed at" an object, and the honest version of that
decision is a table of the instrument names the archive itself emits. Documented lists invent modes
that do not exist and miss ones that do — and HST is the harder case, because the names in a recent
window (13 of them) omit every instrument that has been retired, which is exactly the range the
Sharpless cross-check has to read.

	experiments/instrument_census.py --collection JWST
	experiments/instrument_census.py --collection HST --t-min 55197 --t-max 55532
"""

import argparse
import collections

from astroquery.mast import Observations

# 110 days covers a full JWST cycle's imaging modes at a cost of a few pages, not the whole archive.
DEFAULT_T_MIN, DEFAULT_T_MAX = 60900.0, 61010.0
# A 2010 window: NICMOS and WFPC2 were still in use, so the retired names are measured too.
RETIRED_T_MIN, RETIRED_T_MAX = 55197.0, 55532.0


def census(collection, t_min, t_max):
	"""{instrument_name: rows} for every dataproduct type in the window."""
	rows = Observations.query_criteria(
		obs_collection=[collection], t_min=[t_min, t_max], pagesize=2000)
	counts = collections.Counter(str(name) for name in rows["instrument_name"])
	print(f"=== {collection}: {len(rows)} rows, {len(counts)} instrument names "
		f"(MJD {t_min:.0f}-{t_max:.0f})")
	for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])):
		print(f"  {name:<24} {count}")
	return counts


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--collection", default="JWST", help="HST or JWST")
	parser.add_argument("--t-min", type=float, default=DEFAULT_T_MIN)
	parser.add_argument("--t-max", type=float, default=DEFAULT_T_MAX)
	parser.add_argument("--retired", action="store_true", help="use the 2010 HST window")
	args = parser.parse_args()
	if args.retired:
		args.t_min, args.t_max = RETIRED_T_MIN, RETIRED_T_MAX
	census(args.collection, args.t_min, args.t_max)


if __name__ == "__main__":
	main()
