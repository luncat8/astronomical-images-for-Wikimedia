"""Channel -> RGB colour assignment (plan §5, §7.4). Applied BEFORE the stretch.

A mapping is a data table, not code: per-input weights over R/G/B plus optional
per-input gamma exponents (the non-linear "sensitivity transfer" that separates a
credible narrowband palette from a muddy one). `describe()` produces the exact
mapping string that goes verbatim into the processing log and file description.
"""

from dataclasses import dataclass

import numpy as np


def _expect(cond, message):
	if not cond:
		raise ValueError(message)


@dataclass(frozen=True)
class ColourMapping:
	name: str
	channels: tuple  # input channel names, wavelength-descending for spectral presets
	weights: tuple   # per input: (wr, wg, wb)
	gamma: tuple = ()  # per input exponent, () means all 1.0
	notes: str = ""

	def __post_init__(self):
		_expect(len(self.weights) == len(self.channels),
		        f"{self.name}: {len(self.weights)} weights for {len(self.channels)} channels")
		_expect(not self.gamma or len(self.gamma) == len(self.channels),
		        f"{self.name}: gamma must be empty or one exponent per channel")

	def describe(self) -> str:
		parts = []
		for i, ch in enumerate(self.channels):
			wr, wg, wb = self.weights[i]
			part = f"{ch}->R{wr:g}/G{wg:g}/B{wb:g}"
			if self.gamma and self.gamma[i] != 1.0:
				part += f"(gamma {self.gamma[i]:g})"
			parts.append(part)
		text = f"{self.name}: " + "; ".join(parts)
		if self.notes:
			text += f" [{self.notes}]"
		return text

	def apply(self, channels_img):
		"""channels_img: (n, H, W) normalised linear stack -> (3, H, W) linear RGB."""
		w = np.array(self.weights, dtype=np.float32).T  # (3, n)
		stack = channels_img
		if self.gamma and any(g != 1.0 for g in self.gamma):
			stack = channels_img.copy()
			for i, g in enumerate(self.gamma):
				if g != 1.0:
					# sky-subtracted channels hold negative noise; a fractional power
					# of a negative is NaN, so floor at zero before shaping
					np.maximum(stack[i], 0.0, out=stack[i])
					np.power(stack[i], g, out=stack[i])
		return np.tensordot(w, stack, axes=(1, 0))


def _cm(name, channels, table, gamma=(), notes=""):
	return ColourMapping(name, tuple(channels), tuple(table[ch] for ch in channels),
	                     gamma=gamma, notes=notes)


def build_preset(name, channels):
	n = len(channels)
	if name == "rgb":
		_expect(n == 3, "rgb preset needs R, G, B channels")
		unit = {0: (1.0, 0.0, 0.0), 1: (0.0, 1.0, 0.0), 2: (0.0, 0.0, 1.0)}
		return _cm(name, channels, {ch: unit[i] for i, ch in enumerate(channels)},
		           notes="broadband R->R, G->G, B->B")
	if name == "sho_split":
		_expect(n == 3, "sho_split needs SII, Halpha, OIII")
		return _cm(name, channels, {
			channels[0]: (1.0, 0.0, 0.0),   # SII -> red
			channels[1]: (0.0, 1.0, 0.0),   # Halpha -> green
			channels[2]: (0.0, 0.0, 1.0),   # OIII -> blue
		}, notes="straight one-third split; usually muddy, kept as the labelled baseline")
	if name == "sho_transferred":
		_expect(n == 3, "sho_transferred needs SII, Halpha, OIII")
		return _cm(name, channels, {
			channels[0]: (1.00, 0.15, 0.00),  # SII -> red, slight Halpha bleed
			channels[1]: (0.55, 1.00, 0.00),  # Halpha -> gold (toward green)
			channels[2]: (0.00, 0.35, 1.00),  # OIII -> teal
		}, gamma=(1.0, 0.95, 0.90),
			notes="sensitivity transfer; Halpha mixed toward green, SII toward red")
	if name == "hoo":
		_expect(n == 2, "hoo needs Halpha, OIII")
		return _cm(name, channels, {
			channels[0]: (1.0, 0.38, 0.0),   # Halpha -> gold
			channels[1]: (0.0, 0.62, 1.0),   # OIII -> teal
		}, notes="gold/teal bicolor")
	if name == "dual_synthesis":
		_expect(n == 2, "dual_synthesis needs two filters, longest wavelength first")
		return _cm(name, channels, {
			channels[0]: (1.0, 0.5, 0.0),    # long-wavelength filter -> red + half green
			channels[1]: (0.0, 0.5, 1.0),    # short-wavelength filter -> blue + half green
		}, notes="two-band green synthesised as the average of both")
	if name == "grayscale":
		_expect(n == 1, "grayscale needs one channel")
		return _cm(name, channels, {channels[0]: (1.0, 1.0, 1.0)},
		           notes="single band - no honest colour mapping (plan §5)")
	if name.startswith("spectral_"):
		count = int(name.split("_")[1])
		_expect(n == count, f"{name} needs {count} channels, longest wavelength first")
		return _cm(name, channels, _spectral_table(channels),
		           notes="hues assigned in wavelength order red->violet")
	raise ValueError(f"unknown mapping preset '{name}' for {n} channels")


def _spectral_table(channels):
	hues = np.linspace(0.0, 0.75, len(channels))  # 0=red .. 0.75=violet
	table = {}
	for ch, hue in zip(channels, hues):
		table[ch] = tuple(float(v) for v in _hsv_to_rgb(hue, 1.0, 1.0))
	return table


def _hsv_to_rgb(h, s, v):
	i = int(h * 6.0) % 6
	f = h * 6.0 - int(h * 6.0)
	p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
	return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]


def from_config(cfg, channels):
	"""cfg: {'preset': name} or {'explicit': [[channel, (wr,wg,wb)], ...], 'gamma': [...]}"""
	if "preset" in cfg:
		return build_preset(cfg["preset"], channels)
	if "explicit" in cfg:
		table = {ch: tuple(w) for ch, w in cfg["explicit"]}
		gamma = tuple(cfg.get("gamma", ()))
		return _cm("explicit", channels, table, gamma=gamma)
	raise ValueError("mapping config needs 'preset' or 'explicit'")
