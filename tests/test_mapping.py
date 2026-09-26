import numpy as np
import pytest

from astroproc.mapping import build_preset, from_config


def test_rgb_preset_is_identity():
	m = build_preset("rgb", ("R", "G", "B"))
	assert m.describe() == "rgb: R->R1/G0/B0; G->R0/G1/B0; B->R0/G0/B1 [broadband R->R, G->G, B->B]"
	stack = np.stack([np.full((4, 4), v, dtype=np.float32) for v in (1.0, 2.0, 4.0)])
	rgb = m.apply(stack)
	assert rgb[0].mean() == pytest.approx(1.0)
	assert rgb[1].mean() == pytest.approx(2.0)
	assert rgb[2].mean() == pytest.approx(4.0)


def test_two_band_green_is_the_average():
	m = build_preset("dual_synthesis", ("R", "B"))
	stack = np.stack([np.full((4, 4), 3.0, dtype=np.float32), np.full((4, 4), 1.0, dtype=np.float32)])
	rgb = m.apply(stack)
	assert rgb[1].mean() == pytest.approx(2.0)  # green = (R + B) / 2


def test_hoo_gold_teal_weights():
	m = build_preset("hoo", ("Halpha", "OIII"))
	assert m.weights[0] == (1.0, 0.38, 0.0)
	assert m.weights[1] == (0.0, 0.62, 1.0)


def test_sho_transferred_has_sensitivity_transfer():
	m = build_preset("sho_transferred", ("SII", "Halpha", "OIII"))
	assert m.gamma == (1.0, 0.95, 0.90)
	# Halpha leans toward green to give gold, not a muddy equal split
	assert m.weights[1][1] > m.weights[1][0]


def test_spectral_presets_assign_distinct_hues_in_wavelength_order():
	m = build_preset("spectral_4", ("M1", "M2", "M3", "M4"))
	ws = np.array(m.weights)
	assert ws[0][0] > 0.9   # longest wavelength -> red
	assert ws[-1][2] > 0.9  # shortest -> blue
	# no two adjacent filters share the same hue vector
	for i in range(3):
		assert not np.allclose(ws[i], ws[i + 1])


def test_grayscale_is_white_mapping():
	m = build_preset("grayscale", ("L",))
	rgb = m.apply(np.full((1, 4, 4), 2.0, dtype=np.float32))
	assert np.allclose(rgb[0], rgb[1]) and np.allclose(rgb[1], rgb[2])


def test_explicit_config_mapping():
	m = from_config({"explicit": [["Halpha", (1.0, 0.4, 0.0)], ["OIII", (0.0, 0.6, 1.0)]]},
	                ("Halpha", "OIII"))
	assert m.name == "explicit"
	with pytest.raises(ValueError):
		from_config({}, ("a",))


def test_channel_count_mismatch_raises():
	with pytest.raises(ValueError):
		build_preset("hoo", ("a", "b", "c"))
