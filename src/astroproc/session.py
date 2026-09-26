"""Processing-log recorder (plan §7.9, §13.2).

The log is written while working, not afterwards: the pipeline records each step as it
runs. Fields only a human can supply (operator, licence reasoning, archive path) are
left as explicit TODO markers so their absence is visible, not silent.
"""

import json
import platform
from datetime import datetime, timezone

TEMPLATE = [
	(1, "Source data (archive/own, ID, retrieval date, licence)"),
	(2, "Calibration applied (or: data already calibrated)"),
	(3, "State check: linear / already-stretched / composited / mosaic -> action taken"),
	(4, "Registration + integration (method, dither, alignment)"),
	(5, "Linearisation (required? method, params)"),
	(6, "Background subtraction + channel normalisation (method, values)"),
	(7, "Colour calibration (method, reference, result)"),
	(8, "Saturated-pixel handling"),
	(9, "Colour mapping (exact channel -> colour, incl. any non-linear mapping)"),
	(10, "Stretch (function, shadow clip, iterations, shared across channels: yes/no)"),
	(11, "Background level set to"),
	(12, "Reference check: survey image for orientation (URL); rotation applied"),
	(13, "Star colour check: reference used; result"),
	(14, "Star reduction / denoise (methods, strengths)"),
	(15, "Chromatic aberration correction"),
	(16, "HDR / exposure blending (if used)"),
	(17, "Gradients, sharpening, saturation"),
	(18, "Output colour space, bit depth, banding check"),
	(19, "Data version exported (path) — presentation version exported (path)"),
	(20, "Archive path for FITS + project files"),
	(21, "Licence tag chosen, with the plan §4.3 reasoning"),
]


class Session:
	"""Records steps keyed by the §13.2 template line numbers."""

	def __init__(self, run_name=""):
		self.run_name = run_name
		self.started = datetime.now(timezone.utc)
		self.steps = {}
		self.provenance = {}

	def record(self, num, text):
		self.steps[num] = str(text)

	def provenance_from(self, reports):
		self.provenance = {
			path: report.provenance for path, report in reports.items() if report.provenance
		}

	def software_line(self):
		import numpy, astropy, scipy
		from . import __version__
		return (f"astroproc {__version__}; python {platform.python_version()}; "
		        f"numpy {numpy.__version__}, astropy {astropy.__version__}, scipy {scipy.__version__}")

	def render(self):
		lines = [
			f"# Processing log — {self.run_name}",
			f"Software + versions: {self.software_line()}",
			f"Date processed:      {self.started.isoformat(timespec='seconds')}",
			"Operator:            <TODO: your name>",
			"",
		]
		for num, title in TEMPLATE:
			value = self.steps.get(num, "<TODO: not recorded>")
			lines.append(f"{num:>2}. {title}\n    {value}")
		return "\n".join(lines) + "\n"

	def save(self, out_dir):
		log_path = out_dir / "processing-log.txt"
		log_path.write_text(self.render(), encoding="utf-8", newline="\n")
		params = {
			"run": self.run_name,
			"started": self.started.isoformat(timespec="seconds"),
			"software": self.software_line(),
			"steps": {str(k): v for k, v in sorted(self.steps.items())},
			"provenance": self.provenance,
		}
		json_path = out_dir / "params.json"
		json_path.write_text(json.dumps(params, indent=1) + "\n", encoding="utf-8", newline="\n")
		return log_path, json_path
