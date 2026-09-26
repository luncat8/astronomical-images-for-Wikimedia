import pytest

from astroproc.config import load_config
from astroproc.mapping import from_config
from astroproc.stretch import StretchParams


def write(tmp_path, text):
	path = tmp_path / "run.toml"
	path.write_text(text, encoding="utf-8")
	return path


CONFIG = """
[run]
name = "t"

[inputs]
Halpha = "h.fits"
OIII = "o.fits"

[mapping]
preset = "hoo"

[normalise]
anchor = "Halpha"
throughput = { OIII = 0.85 }
sat_limit = 60000.0

[stretch]
shadow_clip = 0.01
high_point = 2.0
strength = 8.0

[post]
chroma_denoise = 0.3
saturation = 1.1
hdr_cores = true
jpeg = true
"""


def test_load_config_full(tmp_path):
	cfg = load_config(write(tmp_path, CONFIG))
	assert cfg.name == "t"
	assert cfg.anchor == "Halpha"
	assert cfg.throughput == {"OIII": 0.85}
	assert cfg.sat_limit == 60000.0
	assert cfg.stretch_cfg == {"shadow_clip": 0.01, "high_point": 2.0, "strength": 8.0}
	assert cfg.chroma_denoise == 0.3
	assert cfg.hdr_cores and cfg.jpeg
	assert cfg.out_dir.name == "t"


def test_missing_inputs_rejected(tmp_path):
	with pytest.raises(ValueError):
		load_config(write(tmp_path, "[run]\nname='x'\n"))


def test_unknown_anchor_rejected(tmp_path):
	bad = CONFIG.replace('anchor = "Halpha"', 'anchor = "NOPE"')
	with pytest.raises(ValueError):
		load_config(write(tmp_path, bad))


def test_unknown_throughput_channel_rejected(tmp_path):
	bad = CONFIG.replace("OIII = 0.85", "NOPE = 0.85")
	with pytest.raises(ValueError):
		load_config(write(tmp_path, bad))


def test_out_of_range_denoise_rejected(tmp_path):
	bad = CONFIG.replace("chroma_denoise = 0.3", "chroma_denoise = 5.0")
	with pytest.raises(ValueError):
		load_config(write(tmp_path, bad))


def test_stretch_params_explicit_values_win(tmp_path):
	import numpy as np

	from astroproc.config import build_stretch_params

	cfg = load_config(write(tmp_path, CONFIG))
	p = build_stretch_params(cfg, np.full((3, 8, 8), 0.5, dtype=np.float32))
	assert isinstance(p, StretchParams)
	assert p.shadow_clip == 0.01
	assert p.strength == 8.0
	assert p.background_level == 0.03


def test_stretch_params_auto_when_absent(tmp_path):
	import numpy as np

	from astroproc.config import build_stretch_params

	cfg = load_config(write(tmp_path, CONFIG.replace(
		"\n[stretch]\nshadow_clip = 0.01\nhigh_point = 2.0\nstrength = 8.0\n", "")))
	assert cfg.stretch_cfg is None
	rng_img = (np.arange(3 * 16 * 16, dtype=np.float32).reshape(3, 16, 16) % 7) / 7.0
	p = build_stretch_params(cfg, rng_img)
	assert p.high_point > p.shadow_clip > 0.0


def test_out_dir_resolves_like_the_input_paths(tmp_path):
	"""An earlier run wrote its whole output tree outside the project, because the output
	directory was the one path resolved against the shell's working directory."""
	from astroproc.config import load_config

	(tmp_path / "run.toml").write_text('[run]\nname = "r"\n\n[inputs]\nHalpha = "../in.fits"\n'
	                                   '\n[post]\ndir = "../out/r"\n')
	cfg = load_config(tmp_path / "run.toml")
	assert cfg.out_dir == tmp_path.parent / "out" / "r"
	assert cfg.out_dir.is_absolute()


def test_partial_stretch_block_auto_decides_the_missing_keys():
	"""A [stretch] block that only sets the background level must not ship shadow_clip=0,
	high_point=1 — those are defaults in pixels, not in the data's own linear units."""
	import numpy as np
	from pathlib import Path
	from astroproc.config import RunConfig, build_stretch_params
	from astroproc.stretch import auto_params

	rgb = np.linspace(0.0, 10.0, 64 * 64).reshape(64, 64)[None].repeat(3, axis=0)
	auto = auto_params(rgb, background_level=0.02)
	cfg = RunConfig(name="r", inputs={}, mapping_cfg={}, anchor=None, throughput={}, sat_limit=None,
		stretch_cfg={"background_level": 0.02}, background_level=0.02, chroma_denoise=0.0,
		saturation=1.0, hdr_cores=False, jpeg=False, out_dir=Path("."))
	params = build_stretch_params(cfg, rgb)
	assert params.shadow_clip == auto.shadow_clip and params.high_point == auto.high_point
	assert params.high_point > 1.0, "the high point must come from the data, not from the default"
