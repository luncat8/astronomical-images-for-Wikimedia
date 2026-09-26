"""End-to-end demo: synthetic 3-filter scene -> full pipeline -> outputs + log.

Generates FITS with known ground truth (star colours, skies, WCS, one saturated
core), runs the pipeline the same way the CLI does, and prints the audit trail.
Outputs go to experiments/out/ (not committed); the console log is kept in
experiments/logs/.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent / "tests"))

from astroproc.pipeline import run  # noqa: E402
from astroproc.config import load_config  # noqa: E402
from synth import make_scene, write_channels  # noqa: E402


def main():
	(HERE / "logs").mkdir(exist_ok=True)
	out_data = HERE / "out" / "demo-fits"
	channels, truth = make_scene(seed=7, n_stars=80)
	paths = write_channels(channels, out_data, object_name="DEMO-NGC7000")

	config_text = f"""
[run]
name = "demo-sho-synthetic"

[inputs]
SII    = "{paths['SII']}"
Halpha = "{paths['Halpha']}"
OIII   = "{paths['OIII']}"

[mapping]
preset = "sho_transferred"

[normalise]
anchor = "Halpha"
# synthetic sky is roughly proportional to throughput, so sky-matching alone
# equalises object scale; add throughput factors here only if stars read off

[post]
chroma_denoise = 0.3
saturation = 1.05
hdr_cores = true
dir = "{HERE / 'out' / 'demo-sho'}"
"""
	config_path = HERE / "out" / "demo.toml"
	config_path.write_text(config_text, encoding="utf-8")

	cfg = load_config(config_path)
	result = run(cfg)
	print(result.session.render())
	print("\nnotes:")
	for note in result.notes:
		print(" -", note)
	print(f"\noutputs in {cfg.out_dir}")


if __name__ == "__main__":
	main()
