import json

import numpy as np
import pytest
from PIL import Image

from astroproc.config import load_config
from astroproc.pipeline import run

from synth import STAR_COLOURS, make_scene, write_channels


def brightest_wing(rgb, y, x):
	"""Star colour is judged in the wings: the core sits on the stretch asymptote
	where every channel clips to 1.0."""
	offsets = [(3, 0), (-3, 0), (0, 3), (0, -3)]
	pixels = [rgb[:, y + dy, x + dx] for dy, dx in offsets]
	return max(pixels, key=lambda p: float(p.sum()))


def write_config(tmp_path, paths, mapping=None, post=""):
	if mapping is None:  # preset must match the channel count
		mapping = {1: "grayscale", 2: "hoo", 3: "sho_split"}[len(paths)]
	if "dir =" not in post:  # keep the default out dir under tmp_path, never CWD
		post += f'\ndir = "{tmp_path / "out"}"'
	channels = "\n".join(f'{name} = "{path}"' for name, path in paths.items())
	text = f"""
[run]
name = "synth-test"

[inputs]
{channels}

[mapping]
preset = "{mapping}"

[post]
{post}
"""
	path = tmp_path / "run.toml"
	path.write_text(text, encoding="utf-8")
	return path


def test_end_to_end_run(tmp_path):
	channels, _ = make_scene()
	paths = write_channels(channels, tmp_path / "fits")
	cfg = load_config(write_config(tmp_path, paths, post="jpeg = true"))
	result = run(cfg)

	for name in ("data-linear.fits", "data-version-16bit.tif", "presentation.png",
	             "presentation.jpg", "processing-log.txt", "params.json"):
		assert (cfg.out_dir / name).exists(), f"missing {name}"

	img = Image.open(cfg.out_dir / "presentation.png")
	assert img.mode == "RGB" and img.info.get("icc_profile")

	# the §13.2 log: every pipeline-known line filled, human lines visibly TODO
	log = (cfg.out_dir / "processing-log.txt").read_text(encoding="utf-8")
	for must in ("all inputs linear", "Colour mapping", "asinh shared", "banding amplitude"):
		assert must in log
	assert "Operator:" in log and "<TODO" in log
	params = json.loads((cfg.out_dir / "params.json").read_text(encoding="utf-8"))
	assert "9" in params["steps"]  # colour mapping recorded by template number


def test_refuses_stretched_data(tmp_path):
	channels, _ = make_scene()
	stretched = np.clip((channels["Halpha"] - 100.0) / 300.0, 0.0, 1.0) ** 0.4
	channels["Halpha"] = stretched.astype(np.float32)
	paths = write_channels(channels, tmp_path / "fits")
	cfg = load_config(write_config(tmp_path, paths))
	with pytest.raises(SystemExit, match="already-stretched"):
		run(cfg)


def test_star_colours_survive_the_full_pipeline(tmp_path):
	"""Plant blue, white and red stars; the processed image must show them blue, white
	and red. This is the §7 pipeline-order claim tested end to end."""
	channels, truth = make_scene(seed=11, n_stars=60)
	paths = write_channels(channels, tmp_path / "fits")
	cfg = load_config(write_config(
		tmp_path, {"R": paths["Halpha"], "G": paths["OIII"], "B": paths["SII"]},
		mapping="rgb"))
	result = run(cfg, write_outputs=False)

	rgb = result.data_version  # display space, one shared stretch applied
	assert result.linear_rgb.shape[0] == 3
	# exclude the deliberately saturated star: clipped cores carry no colour
	planted = [(y, x, colour) for (y, x, f), colour in zip(truth["stars"], truth["colours"])
	           if 5e3 < f < 3e4]
	assert len(planted) >= 5, f"not enough unsaturated planted stars: {len(planted)}"
	cores = [brightest_wing(rgb, y, x) for y, x, _ in planted]
	classes = [colour for _, _, colour in planted]
	for cls, colour_tuple in STAR_COLOURS.items():
		group = [c for c, colour_class in zip(cores, classes) if colour_class == colour_tuple]
		assert group, f"no planted {cls} stars bright enough"
		for r, g, b in group:
			if cls == "blue":
				assert b > r, f"blue star reads red: {(r, g, b)}"
			if cls == "red":
				assert r > b, f"red star reads blue: {(r, g, b)}"
			if cls == "white":
				assert abs(r - b) < 0.05, f"white star tinted: {(r, g, b)}"


def test_saturation_mask_planted(tmp_path):
	channels, _ = make_scene()
	paths = write_channels(channels, tmp_path / "fits")
	cfg = load_config(write_config(tmp_path, paths))
	result = run(cfg, write_outputs=False)
	assert result.sat_mask is not None
	assert result.sat_mask.any()


def test_verify_writes_no_images(tmp_path):
	channels, _ = make_scene()
	paths = write_channels(channels, tmp_path / "fits")
	cfg = load_config(write_config(tmp_path, paths))
	cfg.out_dir = tmp_path / "nowhere"
	result = run(cfg, write_outputs=False)
	assert "Stretch" in result.session.render()
	assert not (tmp_path / "nowhere").exists()


def test_hdr_cores_step_records(tmp_path):
	channels, _ = make_scene()
	paths = write_channels(channels, tmp_path / "fits")
	cfg = load_config(write_config(tmp_path, paths, post="hdr_cores = true"))
	result = run(cfg, write_outputs=False)
	log = result.session.render()
	assert "low-lift blend" in log or "no saturated pixels" in log
