"""Scoring rubric (plan §6.5) and target dossier rendering (plan §13.1).

The rubric's inputs come from the audit chain: `commons.candidates` decides the gap class (row 2)
and carries the archive's rights field and footprint verdict (rows 1 and 9).

Score 0-3 per row; a 0 on row 1 or row 2 drops the candidate immediately. Rows a machine can judge
are auto-filled from the audit row — three of the ten — and the rest stay explicit, so the shortlist
is argued rather than accumulated: a rubric filled in by the tool that produced the candidate is a
rubric nobody read.
"""

from .commons import ANSWER_VERDICTS, COVERED

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

	def missing(self):
		"""Rows no machine could decide and no operator has judged yet — the shortlist's to-do."""
		return [row for row, value in self.values.items() if value is None]

	def total(self):
		if self.missing():
			raise ValueError(f"unscored rows: {self.missing()}")
		return sum(self.values.values())

	def verdict(self):
		if any(self.values[row] == 0 for row in HARD_GATES):
			return "drop (hard gate)"
		if self.missing():
			return f"incomplete ({_rows(self.missing())} to judge)"
		return "pursue" if self.total() >= 18 else "hold"

	def render(self):
		lines = ["row score criterion", "--- ----- ---------"]
		for row, criterion, why in RUBRIC:
			value = self.values[row]
			lines.append(f"{row:>3} {value if value is not None else '?':>5} {criterion} ({why})")
		if self.missing():
			lines.append(f"total not scored yet: {_rows(self.missing())} "
				f"({', '.join(str(row) for row in self.missing())}) "
				f"{'is' if len(self.missing()) == 1 else 'are'} the operator's "
				f"— rows 3-8 and 10 are judgement, not measurement")
		else:
			lines.append(f"total {self.total()}/30 -> {self.verdict()}")
		return "\n".join(lines)


def _rows(missing):
	return f"{len(missing)} row" if len(missing) == 1 else f"{len(missing)} rows"


def auto_fill(score, row):
	"""Fill the three rows the audit row really answers; leave the other seven blank.

	Row 1, licence: the archive's own rights field decides whether the data may be used at all. A
	proprietary observation is a 0 and a hard gate; a public HST/JWST product is one of the §4.3
	tags, and *which* tag is the operator's call — the gate is answered either way. An empty rights
	field leaves the row blank rather than guessing, because the guess would be the whole gate.

	Row 2, the gap: the Commons verdict, and the only row that can drop a candidate the archive
	audit liked.

	Row 9, feasibility: 3 when a pointed footprint covers the object — the data is already in an
	archive, which is what the row asks.

	Rows 3-8 and 10 are judgement: notability, S/N, colour mode, hard core, framing, reference
	check, educational value. Nothing in a coverage audit measures them.
	"""
	rights = str(row.get("rights", "")).strip().upper()
	if rights:
		score.set(1, 3 if rights == "PUBLIC" else 0)
	gap = str(row.get("gap", ""))
	if gap:
		score.set(2, 0 if gap == COVERED else 3)
	if _covered(row):
		score.set(9, 3)
	return score


def _covered(row):
	""""A pointed footprint covers this object": one of the archive audit's two answering verdicts,
	or a covering count — a CSV round-trip makes every field a string."""
	if str(row.get("verdict", "")) in ANSWER_VERDICTS:
		return True
	return _as_int(row.get("n_covering")) > 0


def _as_int(value):
	try:
		return int(float(value))
	except (TypeError, ValueError):
		return 0


def profile(score, row):
	"""§13.1 dossier fields from one candidate row, `score` filled in; the unknowns stay `<TODO>`.

	The archive's own name goes in as the common name because it is the one that finds the existing
	Commons file — `SH 2-252 F` images as `NGC-2174` — and the dossier is where a reviewer checks
	that. Everything a human has to supply (distance, the reference image, the product level, the
	retrieval date) is left visible rather than filled with something plausible.
	"""
	lead = row.get("lead_image", "")
	evidence = "; ".join(part for part in (
		f"{row.get('n_category_files') or 0} file(s) in {row.get('category')}" if row.get("category") else "",
		f"lead image {lead}" if lead else "",
		f"article {row.get('article')} has no lead image" if row.get("article") and not lead else "",
	) if part) or "no Commons category and no article image: nothing illustrates this object"
	# the frame, the filters and the observation id are the *candidate's* data only when a footprint
	# covers the object: a pointing that missed by 3.84' has a frame size and a filter, and neither
	# is data for this target. `SH 2-7`'s nearest HST frame is 29" of empty sky eight fields away.
	covered = _covered(row)
	fov = str(row.get("fov_arcsec", "")).strip() if covered else ""
	return {
		"designation": row.get("designation", ""),
		# the label first, then the name the archive files the target under; an object with neither
		# gets a visible marker, because an empty pair of parentheses reads as a rendering fault
		"common_name": row.get("label") or row.get("archive_name") or "<TODO>",
		"aliases": ", ".join(_cells(row.get("aliases"))),
		"object_type": row.get("otype", ""),
		"coords": _coords(row),
		"fov": f"{fov} arcsec, frame only" if fov and fov != "-" else "",
		"notability": f"enwiki: {row['article']}" if row.get("article") else "",
		"gap": row.get("gap", ""),
		"gap_evidence": evidence,
		"data_source": _source(row, covered),
		"obs_id": row.get("obs_id", "") if covered else "",
		"licence": f"{row.get('rights')} (archive rights field; tag per plan §4.3)" if row.get("rights") else "",
		"channels": ", ".join(_cells(row.get("filters"))) if covered else "",
		"score": f"{score.total()}/30" if not score.missing() else "",
		"verdict": score.verdict(),
	}


def _source(row, covered):
	"""Where the pixels are, and the name the archive files them under — the second is the one that
	finds an existing Commons file, and the dossier is where a reviewer checks for one.

	When no footprint covered the object, the archive row is still worth carrying: it is the
	observation the operator will find first, and saying that it misses is the difference between a
	shortlist and a false one (§6.3, `SH 2-7`).
	"""
	where = " on ".join(part for part in (str(row.get("instrument", "")).strip(),
		str(row.get("collection", "")).strip()) if part)
	source = f"{where} (MAST archive)" if where else "MAST archive"
	archive_name = str(row.get("archive_name", "")).strip()
	if covered:
		return f"{source}; the archive calls this target {archive_name}" if archive_name else source
	named = f" ({archive_name})" if archive_name else ""
	separated = f" by {row['sep_arcsec']} arcsec" if str(row.get("sep_arcsec", "")).strip() else ""
	return (f"{source}; nearest pointed observation{named} misses the object{separated} — "
		f"the data for this candidate has to come from somewhere else")


def _cells(value):
	"""A CSV cell that holds a list: `;`-separated by `write_candidates` and `write_pointed`."""
	return [cell.strip() for cell in str(value or "").split(";") if cell.strip()]


def _coords(row):
	ra, dec = str(row.get("ra", "")).strip(), str(row.get("dec", "")).strip()
	return f"{ra} {dec} (ICRS)" if ra and dec else ""


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
