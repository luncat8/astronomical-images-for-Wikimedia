"""Linear-space background handling and channel matching (plan §7.3).

All of this runs before any stretch. The sky background is the normalisation anchor:
matching per-channel sky levels is what makes inter-channel colour ratios meaningful.
"""

import numpy as np

from .state import sky_stats


def subtract_sky(img, sigma=3.0, maxiters=10):
	"""Return (image minus clipped sky median, sky median). Copies; input untouched."""
	med, _ = sky_stats(img, sigma=sigma, maxiters=maxiters)
	return img - med, med


def sky_gains(sky_levels, anchor):
	"""Per-channel multiplicative gains that equalise sky levels to the anchor channel.

	sky_levels: {channel: sky median} in linear units (after background subtraction of a
	common offset, or measured directly). Returns {} for a degenerate anchor.
	"""
	ref = sky_levels.get(anchor, 0.0)
	if not ref > 0:
		return {}
	return {name: ref / level for name, level in sky_levels.items() if level > 0}


def match_sky(channels, anchor, throughput=None, sigma=3.0, maxiters=10):
	"""Sky-subtract every channel, then scale to a common sky level.

	channels: {name: 2d array} in linear units.
	throughput: optional {name: factor} for filter-throughput correction (plan §7.3),
	applied on top of the sky match so it is recorded separately.
	Returns (matched {name: array}, record dict for the log).
	Products that already have sky ~0 (e.g. pipeline-background-subtracted) get gain 1.
	"""
	anchor = anchor if anchor in channels else next(iter(channels))
	throughput = throughput or {}
	sub = {}
	sky_before = {}
	for name, img in channels.items():
		sub[name], sky_before[name] = subtract_sky(img, sigma=sigma, maxiters=maxiters)
	gain_map = sky_gains(sky_before, anchor)
	skyless = all(level <= 0 for level in sky_before.values())
	gains = {
		name: (1.0 if skyless else gain_map.get(name, 0.0)) * throughput.get(name, 1.0)
		for name in sub
	}
	matched = {name: arr * gains[name] if gains[name] != 1.0 else arr for name, arr in sub.items()}
	record = {
		"anchor": anchor,
		"sky_before": sky_before,
		"gains (sky match x throughput)": gains,
		"throughput": dict(throughput),
		"note": "all sky levels ~0 - matched to gain 1" if skyless else "",
	}
	return matched, record
