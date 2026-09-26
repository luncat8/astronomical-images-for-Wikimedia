import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from astroproc.export import (
	save_data_version_tiff,
	save_linear_reference,
	save_presentation_jpeg,
	save_presentation_png,
	srgb_icc_bytes,
	to8,
)


def test_to8_rounds_and_clips():
	out = to8(np.array([-0.5, 0.0, 0.5, 1.0, 1.5], dtype=np.float32))
	assert out.tolist() == [0, 0, 128, 255, 255]


def test_srgb_icc_profile_available():
	icc = srgb_icc_bytes()
	assert icc.startswith(b" ICC profile".lstrip()) or icc[:4] == b"acsp" or b"acsp" in icc[:512]


def test_png_embeds_srgb_profile(tmp_path):
	img_data = np.zeros((3, 4, 4), dtype=np.float32)  # channel-first API
	path = tmp_path / "p.png"
	save_presentation_png(path, img_data)
	img = Image.open(path)
	assert img.mode == "RGB"
	assert img.info.get("icc_profile") == srgb_icc_bytes()


def test_data_version_tiff_is_16bit(tmp_path):
	import tifffile

	rng = np.random.default_rng(1)
	img = rng.uniform(0, 1, (3, 8, 8)).astype(np.float32)  # channel-first API
	path = tmp_path / "d.tif"
	save_data_version_tiff(path, img)
	arr = tifffile.imread(path)
	assert arr.dtype == np.uint16
	assert arr.shape == (8, 8, 3)  # written channel-last
	assert arr.max() > 60000  # values survive as 16-bit, not crushed to 8


def test_linear_reference_fits_carries_mapping(tmp_path):
	img = np.full((3, 4, 4), 0.5, dtype=np.float32)
	path = tmp_path / "d.fits"
	save_linear_reference(path, img, [("MAPPING", "test mapping", "channel map")])
	with fits.open(path) as hdus:
		assert hdus[0].data.shape == (3, 4, 4)
		assert hdus[0].header["MAPPING"] == "test mapping"


def test_jpeg_output(tmp_path):
	path = tmp_path / "p.jpg"
	save_presentation_jpeg(path, np.ones((3, 4, 4), dtype=np.float32))
	assert path.exists()


def test_blank_pixels_become_black_instead_of_poisoning_the_cast():
	"""Real drz data has non-finite coverage; np.clip leaves NaN alone and the uint8 cast then
	raises `invalid value encountered in cast`."""
	from astroproc.export import to8

	rgb = np.array([[[np.nan, 0.5], [1.0, 0.0]]])
	out = to8(rgb)
	assert out.dtype == np.uint8
	assert out[0, 0, 0] == 0
	assert out[0, 0, 1] == 128 and out[0, 1, 0] == 255
