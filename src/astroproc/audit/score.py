"""Scoring rubric (plan §6.5) and target dossier rendering (plan §13.1).

Score 0-3 per row; a 0 on row 1 or row 2 drops the candidate immediately. Rows a
machine can judge are auto-filled; the rest stay explicit so the shortlist is argued,
not accumulated.
"""

# (row, criterion, why it matters) — verbatim structure from plan §6.5
RUBRIC = [
	(1, "data licence is clean and identified", "hard gate. No licence, no upload."),
	(2, "a real coverage gap exists (G0/G1/G4)", "the whole point"),
	(3, "the object is notable enough for Commons", "article or catalogue entry editors would plausibly want illustrated"),
	(4, "data is high enough S/N to look good", "3 = abundant, 1 = marginal"),
	(5, "object type suits the colour mode available", "plan §5"),
	(6, "no hard core unless HDR-capable", "clipped cores are the classic amateur failure"),
	(7, "field of view suits the article", "a 0.5 deg frame of a 3 deg object may be worse than useless"),
	(8, "orientation and star colour verifiable", "plan §7.6"),
	(9, "reachable with your equipment or the data is archived", "feasibility"),
	(10, "educational value, not just prettiness", "what an article actually needs"),
]

HARD_GATES = (1, 2)


class Score:
	def __init__(self):
		self.values = {row: None for row, *_ in RUBRIC}

	def set(self, row, value):
		if row not in self.values:
			raise KeyError(f"rubric row {row} does not exist")
		if not 0 <= value <= 3:
			raise ValueError("score is 0..3")
		self.values[row] = value

	def total(self):
		if any(v is None for v in self.values.values()):
			missing = [r for r, v in self.values.items() if v is None]
			raise ValueError(f"unscored rows: {missing}")
		return sum(self.values.values())

	def verdict(self):
		if any(self.values[row] == 0 for row in HARD_GATES):
			return "drop (hard gate)"
		return "pursue" if self.total() >= 18 else "hold"

	def render(self):
		lines = ["row score criterion", "--- ----- ---------"]
		for row, criterion, why in RUBRIC:
			lines.append(f"{row:>3} {self.values[row] if self.values[row] is not None else '?':>5} {criterion} ({why})")
		lines.append(f"total {self.total()}/30 -> {self.verdict()}")
		return "\n".join(lines)


DOSSIER_TEMPLATE = """\
Object:            {designation} ({common_name})   Aliases: {aliases}
Type:              {object_type}   RA/Dec (equinox): {coords}   FOV / scale: {fov}
Distance:          {distance} — {distance_source}   Notable? {notability}
Gap type:          {gap}   Evidence: {gap_evidence}
Colour mode:       {colour_mode}
Data source:       {data_source} — retrieved {retrieved}
Obs ID:            {obs_id}   MAST DOI: {doi}   Data licence: {licence}
Product level:     {product_level}
Channels:          {channels}
Reference image:   {reference}
Score:             {score}
Verdict:           {verdict}
"""


import string

_DOSSIER_KEYS = [field for _, field, _, _ in string.Formatter().parse(DOSSIER_TEMPLATE) if field]


def render_dossier(**fields) -> str:
	filled = {key: str(fields.get(key, "<TODO>")) for key in _DOSSIER_KEYS}
	return DOSSIER_TEMPLATE.format(**filled)
