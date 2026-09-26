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

	p_audit = sub.add_parser("audit", help="coverage audit tooling (plan §6)")
	audit_sub = p_audit.add_subparsers(dest="audit_cmd", required=True)
	p_sparql = audit_sub.add_parser("sparql", help="Wikidata: catalogue objects without P18 image")
	p_sparql.add_argument("--prefix", required=True, help='catalogue code prefix, e.g. "Sh2" or "NGC"; a trailing space is ignored')
	p_sparql.add_argument("--class", dest="p31", default=None, metavar="QID", help='anchor the scan on a Wikidata class, e.g. Q11282 for H II regions; required for space-separated codes such as "SH 2-"')
	p_sparql.add_argument("--limit", type=int, default=200)
	p_mast = audit_sub.add_parser("mast", help="MAST observation coverage for a target list")
	p_mast.add_argument("targets", help="CSV with columns name,ra,dec")

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
		from .audit.sparql import missing_p18

		rows, total = missing_p18(args.prefix, limit=args.limit, p31=args.p31)
		shown = f" (showing {len(rows)})" if len(rows) < total else ""
		scope = f" of class {args.p31}" if args.p31 else ""
		print(f"{total} entries{scope} with a code starting '{args.prefix.strip()}' have no P18 image{shown}:")
		for row in rows:
			print(f"  {format_row(row)}")
		return 0
	if args.audit_cmd == "mast":
		from .audit.mast import coverage
		table = coverage(args.targets)
		print(table)
		return 0
	return 1


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
