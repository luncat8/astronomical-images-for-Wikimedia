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
