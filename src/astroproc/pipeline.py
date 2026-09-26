"""Pipeline orchestration (plan §7, §3.2).

The order below is the correctness argument, not a style preference:
	verify state -> align -> normalise in linear space -> assign colour ->
	ONE shared stretch -> fork (data version) -> post (presentation version).
Each recorded step lands in the §13.2 log; a run = config + log + code version.
"""

from pathlib import Path

import numpy as np

from . import align as align_mod
from . import export, post as post_mod, verify
from .background import match_sky
from .config import RunConfig, RunResult, build_mapping, build_stretch_params
from .session import Session
from .state import classify, header_provenance, load_image
from .stretch import StretchParams, asinh_stretch


def _load_channels(cfg):
	images, headers, reports = {}, {}, {}
	for name, path_str in cfg.inputs.items():
		path = Path(path_str)
		if not path.is_absolute() and cfg.path is not None:
			path = cfg.path.parent / path
		data, header = load_image(path)
		images[name] = np.asarray(data, dtype=np.float32)
		headers[name] = header
		reports[name] = classify(images[name], sat_limit=header.get("SATURATE"))
		reports[name].path = str(path)
		reports[name].provenance = header_provenance(header)
	return images, headers, reports


def run(cfg: RunConfig, write_outputs=True) -> RunResult:
	result = RunResult(config=cfg)
	session = Session(cfg.name)
	result.session = session
	out_dir = cfg.out_dir
	if write_outputs:
		out_dir.mkdir(parents=True, exist_ok=True)

	images, headers, reports = _load_channels(cfg)
	result.notes.extend(
		f"{name}: {report.verdict} (core {report.core_fraction:.4f})"
		for name, report in reports.items()
	)

	# §7.1 state check: never composite stretched data — wrong inter-channel ratios
	stretched = [n for n, r in reports.items() if r.verdict == "stretched"]
	if stretched:
		raise SystemExit(
			f"refusing to process: {stretched} look already-stretched (plan §7.1). "
			"Provide linear products (JWST cal/i2d, HST drz/drc) or an explicit inverse stretch."
		)
	session.record(3, "all inputs linear (histogram core fraction: "
	                  + ", ".join(f"{n} {r.core_fraction:.4f}" for n, r in reports.items()) + ")")
	session.record(2, "archive data assumed calibrated - no own calibration applied (plan §7.2)")
	session.record(5, "not required - inputs verified linear")
	session.provenance_from(reports)
	session.record(1, "; ".join(
		f"{name}: {r.path} [{', '.join(f'{k}={v}' for k, v in sorted(r.provenance.items()))}]; "
		"licence <TODO: record verbatim per plan §4.2>"
		for name, r in reports.items()
	))

	# §7.4 precondition: registration
	wcs_map = {name: align_mod.load_wcs(headers[name]) for name in images}
	reference = cfg.anchor or next(iter(images))
	images, align_text = align_mod.align_channels(images, wcs_map, reference)
	session.record(4, align_text)

	# §7.3 linear normalisation (background subtraction + sky match + throughput)
	matched, norm_record = match_sky(images, reference, cfg.throughput)
	session.record(6, str(norm_record).replace("'", ""))

	# §7.3 saturated pixels: excluded before they can drive the stretch
	channels = list(matched)
	stack = np.stack([matched[n] for n in channels])
	sat_limit = cfg.sat_limit or max(
		(r.sat_limit for r in reports.values() if r.sat_limit), default=None
	)
	sat_mask = (stack >= sat_limit).any(axis=0) if sat_limit else None
	session.record(8, f"limit {sat_limit if sat_limit else 'none found'}; "
	                  f"masked {int(sat_mask.sum()) if sat_mask is not None else 0} px")

	# §7.4 colour assignment BEFORE the stretch
	mapping = build_mapping(cfg, channels)
	linear_rgb = mapping.apply(stack)
	result.mapping, result.linear_rgb = mapping, linear_rgb
	session.record(9, mapping.describe())
	session.record(7, f"sky-matched channels; throughput {cfg.throughput or 'none'}; "
	                  "photometric star-colour calibration not applied - judge by step 13, "
	                  "add factors to [normalise] if stars read off")

	# §7.5 ONE shared stretch
	params = build_stretch_params(cfg, linear_rgb)
	data_version, bg_shift = asinh_stretch(linear_rgb, params)
	result.stretch_params, result.data_version = params, data_version
	session.record(10, params.describe() + f"; background shift {bg_shift:+.4f}")
	session.record(11, f"{params.background_level:g} (display space 0..1)")

	# §7.6 verification
	wcs_ref = wcs_map.get(reference)
	if wcs_ref is not None:
		orientation = verify.orientation_report(wcs_ref, stack.shape[-2:])
		session.record(12, orientation["statement"] if orientation["ok"] else orientation["reason"])
		if orientation["ok"] and abs(orientation["rotation_to_n_up_deg"]) > 0.5:
			result.notes.append(orientation["statement"])
	else:
		session.record(12, "no WCS - verify orientation against a survey reference manually")
	coords, fluxes = verify.detect_stars(linear_rgb, sat_mask=sat_mask)
	colour_report = verify.star_colour_report(fluxes)
	narrowband = any(name in mapping.name for name in ("sho", "hoo", "spectral"))
	guidance = (" narrowband mappings collapse star colour by design - blend broadband "
	            "RGB into the stars or accept the flag (plan §7.6)" if narrowband else "")
	session.record(13, "survey reference <TODO: attach PS1/SDSS cutout>; "
	                  f"{colour_report['statement']}.{guidance}")
	result.notes.append(f"star colour: {colour_report['statement']}{guidance}")

	# §3.2 fork: data version exported before any presentation post
	paths = {
		"linear": out_dir / "data-linear.fits",
		"tiff": out_dir / "data-version-16bit.tif",
		"png": out_dir / "presentation.png",
	}
	if write_outputs:
		prov_cards = [
			(f"PROV{i}", f"{name}: " + ",".join(f"{k}={v}" for k, v in sorted(r.provenance.items())), "input provenance")
			for i, (name, r) in enumerate(reports.items())
		]
		export.save_linear_reference(
			paths["linear"], linear_rgb,
			[("MAPPING", mapping.describe(), "channel -> RGB, applied pre-stretch"),
			 ("STRETCH", params.describe(), "one shared stretch")]
			+ prov_cards
		)
		export.save_data_version_tiff(paths["tiff"], data_version)

	# §7.7 presentation only
	presentation = data_version
	if cfg.chroma_denoise > 0:
		presentation = post_mod.chroma_denoise(presentation, cfg.chroma_denoise)
	session.record(14, f"chroma-only denoise strength {cfg.chroma_denoise:g}; no star reduction")
	ca = post_mod.chromatic_aberration_metric(presentation)
	session.record(15, ca["statement"])
	if cfg.hdr_cores and sat_mask is not None and sat_mask.any():
		short = StretchParams(
			shadow_clip=params.shadow_clip * 2.0,
			high_point=params.high_point,
			strength=params.strength,
			background_level=params.background_level,
		)
		presentation = post_mod.hdr_core_blend(linear_rgb, presentation, sat_mask, short)
		session.record(16, f"low-lift blend (SC {short.shadow_clip:.6g}) into saturated cores, feathered")
	else:
		session.record(16, "no saturated pixels - skipped" if cfg.hdr_cores else "not used")
	presentation = post_mod.saturate(presentation, cfg.saturation)
	session.record(17, f"saturation factor {cfg.saturation:g}; no gradient/sharpening applied")

	# §7.8 QC + presentation outputs
	banding = post_mod.banding_check(presentation)
	session.record(18, f"sRGB (ICC embedded), 8-bit PNG; banding: {banding['statement']}")
	result.presentation = presentation
	result.sat_mask = sat_mask

	session.record(19, f"data: {paths['linear']} + {paths['tiff']}; presentation: {paths['png']}; "
	                   f"log: processing-log.txt + params.json in {out_dir}")
	session.record(20, "<TODO: archive FITS + project files location>")
	session.record(21, "<TODO: licence tag per plan §4.3, with reasoning>")
	if write_outputs:
		export.save_presentation_png(paths["png"], presentation)
		if cfg.jpeg:
			export.save_presentation_jpeg(out_dir / "presentation.jpg", presentation)
		session.save(out_dir)

	return result
