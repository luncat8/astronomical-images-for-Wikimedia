"""Command line: state inspection, pipeline runs, verification, coverage audit."""

import argparse
import sys
from pathlib import Path

from . import __version__


def main(argv=None):
	parser = argparse.ArgumentParser(
		prog="astroproc",
		description="Reproducible scripted chain for colour astronomical images (plan.md §7)",
	)
	parser.add_argument("--version", action="version", version=f"astroproc {__version__}")
	sub = parser.add_subparsers(dest="cmd", required=True)

	p_state = sub.add_parser("state", help="linear vs stretched, saturation, provenance (plan §7.1)")
	p_state.add_argument("files", nargs="+")
	p_state.add_argument("--sat-limit", type=float, default=None)

	p_run = sub.add_parser("process", help="run the pipeline from a TOML config")
	p_run.add_argument("config")
	p_run.add_argument("--out", default=None, help="override output directory")

	p_verify = sub.add_parser("verify", help="run pipeline checks only, write no images")
	p_verify.add_argument("config")
	p_verify.add_argument("--out", default=None, help="override output directory")

	p_audit = sub.add_parser("audit", help="coverage audit tooling (plan §6)")
	audit_sub = p_audit.add_subparsers(dest="audit_cmd", required=True)
	p_sparql = audit_sub.add_parser("sparql", help="Wikidata: catalogue objects without P18 image")
	p_sparql.add_argument("--prefix", required=True, help='catalogue code prefix, e.g. "Sh2" or "NGC"; a trailing space is ignored')
	p_sparql.add_argument("--class", dest="p31", default=None, metavar="QID", help='anchor the scan on a Wikidata class, e.g. Q11282 for H II regions; required for space-separated codes such as "SH 2-"')
	p_sparql.add_argument("--limit", type=int, default=200)
	p_sparql.add_argument("--out", default=None, help="write the shortlist as CSV, the input to `audit coords`")
	p_mast = audit_sub.add_parser("mast", help="MAST observation coverage for a target list")
	p_mast.add_argument("targets", help="CSV with columns name,ra,dec")
	p_mast.add_argument("--radius", type=float, default=0.01, help="cone radius in degrees (0.01 = 36 arcsec)")
	p_pointed = audit_sub.add_parser(
		"pointed", help="did a pointed observation image each target, and what does the archive call it"
	)
	p_pointed.add_argument("targets", help="CSV with columns name,ra,dec")
	p_pointed.add_argument("--radius", type=float, default=0.2,
		help="cone radius in degrees; wide, because a pointing that misses is still worth reading")
	p_pointed.add_argument("--all-modes", action="store_true",
		help="count acquisition and spectroscopy modes as pointed (they are not pictures)")
	p_pointed.add_argument("--out", default=None, help="write the rows as CSV")

	p_coords = audit_sub.add_parser(
		"coords", help="resolve designations to coordinates — the input the MAST check needs"
	)
	source = p_coords.add_mutually_exclusive_group(required=True)
	source.add_argument("--prefix", help="run the Wikidata gap audit for this prefix and resolve it")
	source.add_argument("--csv", help="designation CSV, e.g. from `audit sparql --out gaps.csv`")
	p_coords.add_argument("--class", dest="p31", default=None, metavar="QID", help="class anchor, e.g. Q11282 for H II regions")
	p_coords.add_argument("--limit", type=int, default=200)
	p_coords.add_argument("--out", default="-", help="target CSV to write, '-' for stdout")
	p_coords.add_argument("--no-aliases", action="store_true", help="do not retry unresolved names with their cross-identifications")

	args = parser.parse_args(argv)
	if args.cmd == "state":
		return cmd_state(args)
	if args.cmd == "process":
		return cmd_process(args)
	if args.cmd == "verify":
		return cmd_verify(args)
	if args.cmd == "audit":
		return cmd_audit(args)
	return 1


def cmd_state(args):
	# astropy comes in with the command it needs, so the audit needs only requests.
	from .state import inspect_file

	for path in args.files:
		report = inspect_file(path, sat_limit=args.sat_limit)
		print(report.summary())
		print()
	return 0


def cmd_process(args):
	from . import pipeline
	from .config import load_config

	cfg = load_config(args.config)
	if args.out:
		cfg.out_dir = Path(args.out)
	result = pipeline.run(cfg)
	for note in result.notes:
		print(f"note: {note}")
	print(f"done: outputs in {cfg.out_dir}")
	return 0


def cmd_verify(args):
	from . import pipeline
	from .config import load_config

	cfg = load_config(args.config)
	if args.out:
		cfg.out_dir = Path(args.out)
	result = pipeline.run(cfg, write_outputs=False)
	print(result.session.render())
	return 0


def cmd_audit(args):
	if args.audit_cmd == "sparql":
		from .audit.sparql import missing_p18, write_gaps

		rows, total = missing_p18(args.prefix, limit=args.limit, p31=args.p31)
		shown = f" (showing {len(rows)})" if len(rows) < total else ""
		scope = f" of class {args.p31}" if args.p31 else ""
		print(f"{total} entries{scope} with a code starting '{args.prefix.strip()}' have no P18 image{shown}:")
		for row in rows:
			print(f"  {format_row(row)}")
		if args.out:
			write_gaps(rows, args.out)
			print(f"wrote {args.out}", file=sys.stderr)
		return 0
	if args.audit_cmd == "mast":
		from .audit.mast import coverage
		table = coverage(args.targets, radius_deg=args.radius)
		print(table)
		skipped = table.meta["skipped_without_coords"]
		if skipped:
			print(f"{skipped} target(s) had no coordinates and were skipped — resolve them first (`audit coords`)")
		return 0
	if args.audit_cmd == "pointed":
		return cmd_pointed(args)
	if args.audit_cmd == "coords":
		return cmd_coords(args)
	return 1


def cmd_pointed(args):
	"""The three tests of §6.3.1, in order, one line per target."""
	from .audit.mast import pointed, write_pointed

	rows = pointed(args.targets, radius_deg=args.radius, imaging_only=not args.all_modes)
	for row in rows:
		print(format_pointed(row))
	candidates = [row for row in rows if row["verdict"] == "imaged"]
	others = sum(row.get("n_other", 0) for row in rows)
	no_coords = sum(row["verdict"] == "no_coordinates" for row in rows)
	skipped = sum(row["verdict"] == "no_pointed_data" for row in rows)
	print(f"\n{len(candidates)} target(s) imaged by a pointed observation, "
		f"{skipped} with no pointed observation in the cone, {no_coords} unresolved")
	if others:
		print(f"{others} observation(s) excluded as acquisition, spectroscopy or unknown mode", file=sys.stderr)
	if args.out:
		write_pointed(rows, args.out)
		print(f"wrote {args.out}", file=sys.stderr)
	return 0


def format_pointed(row):
	"""Audit line: what the archive calls the target, and whether the footprint landed on it.

	The archive's own name is printed first because it is the answer the audit is for: `SH 2-252 F`
	images as `NGC-2174`, which is how the object is already illustrated on Commons.
	"""
	if row["verdict"] == "no_coordinates":
		return f"  {row['target']}  no coordinates — resolve it first (`audit coords`)"
	if row["verdict"] == "no_pointed_data":
		return f"  {row['target']}  no pointed observation in the cone ({row['n_other']} other mode(s))"
	separation = _separation_text(row)
	return (f"  {row['target']}  archive: {row['archive_name']}  {row['instrument']} {row['filters']} "
		f"FOV {row['fov_arcsec']}\"  {separation}  {row['n_covering']}/{row['n_pointed']} covering"
		f"  {row['obs_id']} (programme {row['proposal']}, {row['pi']}, public {row['public']})")


def _separation_text(row):
	if row["n_covering"]:
		return "inside a footprint"
	if row["sep_arcsec"] is None:
		return "footprint unreadable"
	return f"{row['sep_arcsec']} arcsec outside"


def cmd_coords(args):
	"""Designations -> coordinates -> the target CSV that `audit mast` reads."""
	from .audit import coords

	if args.csv:
		rows = coords.resolve_csv(args.csv, use_aliases=not args.no_aliases)
		total = len(rows)
	else:
		rows, total = coords.resolve_gaps(args.prefix, p31=args.p31, limit=args.limit,
			use_aliases=not args.no_aliases)
	shown = f" (shortlist of {len(rows)} of {total})" if len(rows) < total else ""
	print(f"{total} gap designations{shown}, resolved {sum(row['ra'] is not None for row in rows)}:", file=sys.stderr)
	for row in rows:
		if row["ra"] is not None:
			print(f"  {row['name']}  {row['ra']:.5f} {row['dec']:+.5f}  {row['otype'] or '?'}  {row['object']}  via {row['via']}", file=sys.stderr)
	missing = [row["name"] for row in rows if row["ra"] is None]
	if missing:
		print(f"unresolved ({len(missing)}): {', '.join(missing)}", file=sys.stderr)

	coords.write_targets(rows, args.out)
	if args.out != "-":
		print(f"wrote {args.out}", file=sys.stderr)
	return 0


def format_row(row):
	"""Audit line: id, name, designation, aliases, coordinates.

	Aliases matter more than they look: the same nebula is filed under several catalogues,
	and a gap under one designation is often already covered under another (§6.2).
	"""
	name = row["label"] or "-"
	aliases = f"  also: {', '.join(row['aliases'])}" if row["aliases"] else ""
	coords = f"{row['ra']:.5f} {row['dec']:+.5f}" if "ra" in row else "no coordinates"
	return f"{row['item']}  {name}  [{'; '.join(row['codes'])}]{aliases}  {coords}"


if __name__ == "__main__":
	sys.exit(main())
