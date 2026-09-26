"""The one shared stretch (plan §7.5).

Same function, same parameters, applied to the whole RGB composite — independent
per-channel stretching is the number-one cause of "unnatural colours" in review.
asinh with a recorded shadow-clip (SC) and high point (HP); background then lands on
a recorded level so the result is reproducible.

The hot path works in-place on one scratch buffer (AGENTS.md: no avoidable allocations).
"""

import math
from dataclasses import dataclass

import numpy as np
from astropy.stats import sigma_clipped_stats

from .state import sky_stats


@dataclass(frozen=True)
class StretchParams:
	shadow_clip: float   # linear units; below SC -> black
	high_point: float    # linear units; asymptotic white reference
	strength: float      # asinh softening: y = asinh(u*s)/asinh(s), u=(x-SC)/(HP-SC)
	background_level: float  # display-space sky target, e.g. 0.03

	def describe(self) -> str:
		return (f"asinh shared across channels: shadow_clip={self.shadow_clip:.6g}, "
		        f"high_point={self.high_point:.6g}, strength={self.strength:g}, "
		        f"background_level={self.background_level:g}")


def auto_params(linear_rgb, background_level=0.03, strength=10.0, sc_sigma=0.7):
	"""SC just above the sky (lifts the faint tail), HP at the 99.9th percentile of the
	composite luminance. Returned values are frozen into the log — auto only runs once.

	Blank coverage is excluded, as everywhere else: `np.percentile` returns NaN when a single
	percentile lands on one non-finite pixel, and a NaN high point silently turns the whole
	composite into blank coverage through the stretch (measured 2026-09-26 on a real drz frame
	with 1.3 % NaN at the edge).
	"""
	lum = linear_rgb.mean(axis=0) if linear_rgb.ndim == 3 else linear_rgb
	pixels = lum[np.isfinite(lum)]
	sky, std = sky_stats(pixels)
	high = float(np.percentile(pixels, 99.9))
	sc = sky + sc_sigma * max(std, 1e-12)
	hp = max(high, sc * 1.5 + 1e-12)
	return StretchParams(float(sc), hp, strength, background_level)


def asinh_stretch(linear_rgb, params, background_target=None):
	"""Apply the shared stretch. Returns (display RGB in [0, 1], applied background shift).

	Monotone in the input: equal linear pixels map to equal display pixels across all
	channels — that property IS the colour-correctness argument (plan §7 order).
	"""
	sc, hp, s = params.shadow_clip, params.high_point, params.strength
	norm = math.asinh(s)
	work = np.subtract(linear_rgb, sc, dtype=np.float32)
	work /= np.float32(hp - sc)
	work *= np.float32(s)
	np.arcsinh(work, out=work)
	work /= np.float32(norm)
	np.clip(work, 0.0, 1.0, out=work)

	if background_target is None:
		background_target = params.background_level
	# strided subsample: a median over ~4M samples is statistically identical to the
	# full array and avoids a multi-hundred-MB sigma-clip copy of the composite
	stride = max(1, int(np.ceil(np.sqrt(work.size / 4e6))))
	sample = work[:, ::stride, ::stride] if work.ndim == 3 else work[::stride, ::stride]
	_, sky_out, _ = sigma_clipped_stats(sample, sigma=3.0, maxiters=5)
	shift = float(background_target) - float(sky_out)
	if shift != 0.0:
		work += np.float32(shift)
		np.clip(work, 0.0, 1.0, out=work)
	return work, shift
