"""Outputs (plan §3.2, §7.8, §8): linear reference, 16-bit data version, presentation PNG.

The data version is exported before any presentation post; the presentation version is
8-bit sRGB with an embedded ICC profile (untagged non-sRGB is a listed Commons defect).
"""

from functools import lru_cache

import numpy as np
import tifffile
from astropy.io import fits
from PIL import Image, ImageCms

@lru_cache(maxsize=1)
def srgb_icc_bytes() -> bytes:
	return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def to8(rgb01):
	return (np.clip(rgb01, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _hwc(rgb01):
	"""(3, H, W) channel-first -> (H, W, 3) channel-last for PIL/tifffile writers."""
	rgb01 = np.asarray(rgb01)
	return (np.transpose(rgb01, (1, 2, 0)) if rgb01.ndim == 3 else rgb01)


def save_linear_reference(path, linear_rgb, header_cards):
	"""32-bit float FITS cube of the composite before the stretch — the reviewer's check."""
	hdu = fits.PrimaryHDU(np.asarray(linear_rgb, dtype=np.float32))
	for card, value, comment in header_cards:
		hdu.header[card] = (value, comment)
	hdu.writeto(path, overwrite=True)


def save_data_version_tiff(path, rgb01):
	"""16-bit RGB TIFF of the stretched data version (plan §7.8: keep a 16-bit master)."""
	data = (np.clip(_hwc(rgb01), 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)
	tifffile.imwrite(path, data, photometric="rgb", metadata=None)


def _image8(rgb01):
	arr = np.ascontiguousarray(to8(_hwc(rgb01)))
	assert arr.shape[2] == 3 and arr.dtype == np.uint8
	return Image.fromarray(arr)  # uint8 (H, W, 3) infers mode RGB


def save_presentation_png(path, rgb01):
	img = _image8(rgb01)
	img.save(path, icc_profile=srgb_icc_bytes())
	return img


def save_presentation_jpeg(path, rgb01, quality=95):
	img = _image8(rgb01)
	img.save(path, quality=quality, icc_profile=srgb_icc_bytes())
	return img
