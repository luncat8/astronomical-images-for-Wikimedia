"""Command line: state inspection, pipeline runs, verification, coverage audit."""

import argparse
import sys
from pathlib import Path

from . import __version__, pipeline
from .config import load_config
from .state import inspect_file


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
	p_sparql.add_argument("--prefix", required=True, help='catalogue code prefix, e.g. "Sh2 "')
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
	for path in args.files:
		report = inspect_file(path, sat_limit=args.sat_limit)
		print(report.summary())
		print()
	return 0


def cmd_process(args):
	cfg = load_config(args.config)
	if args.out:
		cfg.out_dir = Path(args.out)
	result = pipeline.run(cfg)
	for note in result.notes:
		print(f"note: {note}")
	print(f"done: outputs in {cfg.out_dir}")
	return 0


def cmd_verify(args):
	cfg = load_config(args.config)
	if args.out:
		cfg.out_dir = Path(args.out)
	result = pipeline.run(cfg, write_outputs=False)
	print(result.session.render())
	return 0


def cmd_audit(args):
	if args.audit_cmd == "sparql":
		from .audit.sparql import missing_p18
		rows = missing_p18(args.prefix, limit=args.limit)
		print(f"{len(rows)} objects with catalogue code starting '{args.prefix}' have no P18 image:")
		for row in rows:
			coords = f"{row.get('ra', '')} {row.get('dec', '')}".strip()
			print(f"  {row['item']}  {row.get('label', '')}  {coords}")
		return 0
	if args.audit_cmd == "mast":
		from .audit.mast import coverage
		table = coverage(args.targets)
		print(table)
		return 0
	return 1


if __name__ == "__main__":
	sys.exit(main())
