"""Run configuration (TOML) — the reproducibility contract (plan §7.9, §12 D3).

A run = config file + code version + auto-filled §13.2 log. Any third party can rebuild
the composite from the published data plus this file.

Example
-------
	[run]
	name = "demo-sh2-xxx"

	[inputs]                     # channel name -> FITS path, longest wavelength first
	Halpha = "fits/halpha.fits"
	OIII   = "fits/oiii.fits"

	[mapping]
	preset = "hoo"               # or explicit = [["Halpha", [1.0, 0.38, 0.0]], ...]

	[normalise]
	anchor = "Halpha"            # default: first input
	throughput = { OIII = 0.85 } # optional filter-throughput factors

	[stretch]                    # omit to let auto_params decide (values still recorded)
	shadow_clip = 0.012
	high_point = 3.5
	strength = 10.0
	background_level = 0.03

	[post]
	chroma_denoise = 0.0         # 0..1
	saturation = 1.0
	hdr_cores = false            # blends a low-lift stretch into saturated cores
	jpeg = false
"""

import tomllib
from dataclasses import dataclass, field
import os
from pathlib import Path

import numpy as np

from .mapping import ColourMapping, from_config
from .stretch import StretchParams, auto_params


@dataclass
class RunConfig:
	name: str
	inputs: dict                      # channel -> path
	mapping_cfg: dict                 # {'preset': ...} or {'explicit': ...}
	anchor: str | None
	throughput: dict
	sat_limit: float | None           # saturation limit; header SATURATE is the fallback
	stretch_cfg: dict | None          # None -> auto
	background_level: float
	chroma_denoise: float
	saturation: float
	hdr_cores: bool
	jpeg: bool
	out_dir: Path
	path: Path | None = None


def _expect(cond, message):
	if not cond:
		raise ValueError(message)


def load_config(path) -> RunConfig:
	path = Path(path)
	raw = tomllib.loads(path.read_text(encoding="utf-8"))
	run = raw.get("run", {})
	inputs = raw.get("inputs", {})
	_expect(inputs, "[inputs] needs at least one channel = FITS path")
	_expect(len(set(inputs)) == len(inputs), "duplicate channel names")

	norm = raw.get("normalise", {})
	anchor = norm.get("anchor")
	_expect(anchor is None or anchor in inputs, f"normalise.anchor '{anchor}' is not an input channel")
	throughput = {k: float(v) for k, v in norm.get("throughput", {}).items()}
	_expect(set(throughput) <= set(inputs), "normalise.throughput has unknown channel names")
	_expect(all(v > 0 for v in throughput.values()), "throughput factors must be positive")
	sat_limit = norm.get("sat_limit")
	_expect(sat_limit is None or float(sat_limit) > 0, "normalise.sat_limit must be positive")

	stretch_cfg = raw.get("stretch", None) or None
	if stretch_cfg is not None:
		known = {"shadow_clip", "high_point", "strength", "background_level"}
		_expect(set(stretch_cfg) <= known, f"stretch keys must be within {sorted(known)}")

	post = raw.get("post", {})
	cd = float(post.get("chroma_denoise", 0.0))
	_expect(0.0 <= cd <= 1.0, "post.chroma_denoise must be 0..1")
	# Relative to the config file, like every input path: resolving it against the shell's
	# working directory instead sent a run's whole output tree outside the project, because the
	# process happened to be started from the repository root.
	out_dir = Path(post.get("dir", run.get("name", "run")))
	if not out_dir.is_absolute():
		# normpath, not resolve: it collapses ".." so the log and params.json carry a readable
		# path, without following symlinks into a name the user never typed.
		out_dir = Path(os.path.normpath(path.parent / out_dir))

	return RunConfig(
		name=run.get("name", path.stem),
		inputs=dict(inputs),
		mapping_cfg=raw.get("mapping", {}),
		anchor=anchor,
		throughput=throughput,
		sat_limit=float(sat_limit) if sat_limit else None,
		stretch_cfg=stretch_cfg or None,
		background_level=float((stretch_cfg or {}).get("background_level", 0.03)),
		chroma_denoise=cd,
		saturation=float(post.get("saturation", 1.0)),
		hdr_cores=bool(post.get("hdr_cores", False)),
		jpeg=bool(post.get("jpeg", False)),
		out_dir=out_dir,
		path=path,
	)


def build_stretch_params(cfg: RunConfig, linear_rgb):
	"""Explicit values from the config, or auto — either way the numbers are frozen
	into the log, so a reviewer sees exactly what was applied."""
	chosen = {k: float(v) for k, v in (cfg.stretch_cfg or {}).items()}
	# Per key, not per section: a [stretch] block that only sets the background level must not
	# silently ship shadow_clip=0 and high_point=1 in linear units. Those defaults are 0 and 1
	# *pixels*, and on a real product in electrons/s they compress the object into the top
	# octave of the display range (measured 2026-09-26 on WFC3/IR data), with nothing in the
	# log saying the numbers were never chosen.
	auto = auto_params(linear_rgb, background_level=cfg.background_level)
	values = {key: chosen.get(key, getattr(auto, key)) for key in
		("shadow_clip", "high_point", "strength", "background_level")}
	return StretchParams(**values)


def build_mapping(cfg: RunConfig, channels) -> ColourMapping:
	return from_config(cfg.mapping_cfg, channels)


@dataclass
class RunResult:
	config: RunConfig
	linear_rgb: np.ndarray = None
	data_version: np.ndarray = None
	presentation: np.ndarray = None
	stretch_params: StretchParams = None
	session: object = None
	mapping: ColourMapping = None
	sat_mask: np.ndarray = None
	notes: list = field(default_factory=list)
