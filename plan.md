# Plan: producing original colour astronomical images for Wikimedia

Merged from the four plans compared in `comparison.md` (`plan.md`, `b.md`, `a.md`,
`GPT2026.md`): `plan.md`'s technical spine, `b.md`'s actionable licensing and batch audit,
`GPT2026.md`'s archive-product and two-output material, `a.md`'s accessibility — with the errors
those plans contained corrected rather than averaged in. Policy and licence-template statements
are dated because they drift; §15 lists what to re-read before the first upload.

---

## 0. The short version

1. **The target is not "an un-colourised image"** — it is *an object with no adequately covered,
   freely-licensed, correctly-oriented image*. Five-way gap taxonomy, §6.1; candidates live in the
   data archives, not the image galleries.
2. **The data licence is the gate**, not the licence of the picture you found (§4). Colourising
   someone else's data makes you a derivative author; you gain no new rights.
3. **No AI/ML anywhere** — no colourisation, neural denoise, upscaling, or generative star
   replacement (§2). Commons policy names black-and-white colourisation specifically.
4. **The pipeline order is the correctness argument:** linearise → normalise → assign colour →
   **one shared stretch** → post (§7). Reversing stretch and colour is the most common technical
   reason a colour astro image is rejected as "unnatural colours".
5. **Single-band data ⇒ publish grayscale** (§5). A tint implies colour information that is not there.
6. **Verify orientation and star colour against a survey reference before publishing** (§7.6) —
   highest value, lowest cost in the pipeline.
7. **Documentation is the deliverable** (§7.9, §13.2), and **two outputs** — a data version and a
   presentation version (§3.2) — answer the faithfulness objection before it is raised.
8. **Do not compete with the mission press offices** for the famous ~200 objects (§6.6), and if you
   want to start producing today, §14.1 is the smallest viable first upload.

---

## 1. Entry points

The task defines three starting situations. They differ almost entirely in **§6 (finding a
target)** and not at all in the gates (§2–§4), the pipeline (§7), the QA bar (§8) or publishing
(§9). Pick your row; the rest applies unchanged.

**0.A — "this object has no photo on Wikipedia."** Get coordinates and **all** aliases from the
article and from **SIMBAD** (one galaxy can be NGC / UGC / PGC / IC / Arp / Mrk; searching one
designation is how people wrongly conclude "no image exists"). Then check coverage in this order:
Wikidata **P18** → Commons (every designation *and* alias) → official galleries (esahubble.org,
esawebb.org, science.nasa.gov, ESO, NOIRLab, Chandra) → community processing sites (AstroBin,
Flickr, TinEye). **A quick-look preview is not a finished image** — an automatic colour preview in
the Hubble Legacy Archive or ESASky is still an opportunity. If a decent image already exists,
the highest-value contribution is a **better** one, not a second one; prefer a modest,
well-scaled object over a famous one. If nothing exists: confirm usable data (§6.3), confirm
licence (§4), process. A single filter is not a failure — it is a grayscale upload (§5).

**0.B — "I have a catalogue object and want to check and act."** Do it as a **batch**. Wikidata
SPARQL finds catalogue entries with no image at all:

```sparql
SELECT ?item ?itemLabel WHERE {
  ?item wdt:P528 ?cat .            # catalogue code
  FILTER(STRSTARTS(?cat, "NGC "))
  FILTER NOT EXISTS { ?item wdt:P18 ?img }
}
LIMIT 500
```

Cross-check the resulting coordinates against MAST / ESASky for actual imaging coverage — MAST
accepts an uploaded target list, which turns this into a to-do list of *objects that have data but
no picture*. Triage with SkyView or a PS1 cutout first to discard single stars, duplicates and
asterisms. Score the survivors (§6.5) and commit to 5–10 targets. Processing 300 candidates is the
classic failure mode.

**0.C — "I just want to produce something new."** Two different games; choose deliberately.
*Learn the chain safely* (recommended first): take a famous object that already has an excellent
Commons colour image, reprocess the **same public FITS**, and compare side by side. You learn
every step against a known-good answer and you cannot damage anything by uploading. Then do a real
0.A/0.B target. *Or hunt for genuinely new imagery*: recently released multi-filter MAST data, or
a target that has never appeared in a press release — the most interesting version being a
multi-filter **infrared** target with no public composite (§5.3, §12 D2). Do **not** hunt
"background galaxies hidden in large fields" without the notability screen (§6.5 row 3): such an
object is very likely out of scope for Commons no matter how well it is processed.

---

## 2. Gate 1 — no AI/ML anywhere in the chain

Position as of 2026 (re-check per §15): Commons policy work on AI content requires AI-generated
works to be **marked in-image** and discernible in a 250px thumbnail, and AI-**altered** works to
have the **unmodified original uploaded and linked** from the file page (`{{AI modified}}`,
`{{AI upscaled}}`). Commons guidance on AI media states that generative AI "is unable to reliably
upscale small photographs **or colorize black and white photographs** without introducing
significant errors or fabrications" — verbatim the operation contemplated here. `Commons:Upscaling`
discourages AI upscaling specifically and upscaling is out of scope except in narrow cases, and a
live Meta-Wiki RfC is tightening AI-disclosure across Wikimedia.

**Decision: no AI/ML in any step** — not colourisation, neural denoise, upscaling, generative star
replacement, or "neural style transfer to make an Hα frame look like a Hubble image". The
deliverable is an *illustrative scientific record*; fabricated detail is a defect however
convincing it looks. The "gold" Hubble look is achievable deterministically: a sensitivity-transfer
function plus a documented colour mapping, nothing more.

---

## 3. Gate 2 — upscaling, and the two-output structure

**3.1 No upscaling.** Never upload a resized version of a composite as if it were higher
resolution; if a mosaic or larger field exists, capture it. QI/FP files may not be overwritten, so
**fix resolution before promoting, not after**.

**3.2 Produce two outputs, not one.** Everything up to and including the shared stretch (§7.5) is the
**data version** — the thing a reviewer can check. Everything in §7.7 is the **presentation
version** — the file that competes in an article. Fork at that point, keep the data version
untouched, and link it (or a linear/grayscale reference) from the file page. ESA/Hubble itself
notes its attractive public images involve selection, colour assignment and dynamic-range
adjustment rather than being photographs straight from the telescope, so this split is how you stay
honest about that without under-delivering visually. It materially speeds up review.

---

## 4. Gate 3 — rights, licence and provenance

Do this **before** processing. It decides whether the work can ever be published, and it is
routinely skipped.

### 4.1 The rule that trips people up

**Colourising someone else's grayscale data makes you a derivative author, not the author.** You
gain no new rights. If the source is CC BY 4.0, your composite must comply with CC BY 4.0 —
credit, link the licence, note changes. You cannot convert it to CC0 and you cannot unilaterally
move it to CC BY-SA. This determines the licence tag you actually put on the file, and it is the
most common licence mistake in amateur Wikimedia uploads.

### 4.2 Source licence table

| Source | Usual status for Commons | Notes |
|---|---|---|
| **Your own telescope** | **yours — cleanest position** | least friction, most defensible provenance |
| **ESO Science Archive** | **CC BY 4.0**, raw *and* processed | ESO retains copyright; the required credit statement must be preserved. Check the archive's data-access terms. |
| **NOIRLab Astro Data Archive** | **CC BY 4.0** (confirm per collection) | archive *images* are CC BY 4.0; papers, code and text are explicitly **not**. |
| **ESA/Hubble, ESA/Webb material** | **CC BY 4.0** for post-cutoff/site material | §4.3 — where most plans get this wrong |
| **NASA/STScI material** | generally not copyrighted | but see the Hubble/Webb caveat in §4.3 |
| **DSS / DSS2** | **AVOID** | free to *look at*, not free to reuse — see below |
| **SDSS, Pan-STARRS, Legacy Surveys**, and survey cutout *services* (SkyView, PS1 cutouts, SkyServer) | **check current policy; cutouts frequently non-free for direct reuse** | widely used on Commons but not automatically free. Excellent as reference/orientation material — triage with them, do not publish from them. |
| **Zenodo / author-released data** | clean **if** deposited under an explicit CC licence | get the licence in writing, not from a README claim |
| **arXiv, journal supplementary data, APOD, competitions, social media, personal sites** | **copyrighted** | not a safe source unless a CC record exists; inspiration and orientation only. Never a source. |

**DSS is the trap most plans miss.** The Digitized Sky Survey is often listed as "free, public
domain" because it is free to *look at*. It is not free to reuse: the POSS-II-based northern files
are "copyright © 1993–1995 by the California Institute of Technology… All Rights Reserved", and
the southern UK Schmidt / AAO plates are "© 1993–5 by the Anglo-Australian Observatory Board" or
jointly "© 1992–5, jointly by the UK SERC/PPARC and the Anglo-Australian Telescope Board… All
Rights Reserved" (STScI DSS copyright page; mirrored by ESO and NED). STScI's guidance is to
contact the originating institutions for permission, and states that commercial use of these data
is prohibited without it. **Practical tip: the copyright status of an individual plate is recorded
in the FITS header of the file you downloaded** — read it there rather than assuming.

Preference order, best to worst: (1) your own data; (2) raw FITS from a public archive under CC BY
4.0 or public domain; (3) author-released data on Zenodo under an explicit CC licence, in writing;
(4) anything else — needs individual legal judgement.

### 4.3 Hubble / Webb licence decision rule (verified 2026-09-26)

Self-processing NASA/STScI data is **not** automatically public domain. The templates say so
explicitly:

| Situation | Correct tag | Why |
|---|---|---|
| NASA Hubble material, or ESA Hubble material **prior to 2009** | `{{PD-Hubble}}` | the tag "does not apply if ESA material created after 2008" |
| ESA Hubble material **2009 or later** on spacetelescope.org | `{{ESA-Hubble}}` (CC BY 4.0) | `{{PD-Hubble}}` itself redirects here |
| Self-processed HST composite from **STScI-produced** data | `{{PD-Hubble}}` / `{{PD-USGov-NASA}}` may apply | but `{{PD-USGov-NASA}}` warns: "Materials based on Hubble Space Telescope data may be copyrighted if they are not explicitly produced by the STScI" |
| NASA JWST material | `{{PD-Webb}}` | does not apply "if source material from other organizations is in use" |
| ESA JWST material created on esawebb.org | `{{ESA-Webb}}` (CC BY 4.0) | `{{PD-Webb}}` redirects here — note the Webb split is by **site**, not by year |
| ESO / NOIRLab data and press imagery | `{{Cc-by-4.0}}` + the required credit statement | attribution required |
| Third-party instruments in the same archive | check that instrument's terms | all the PD tags disclaim other organisations' material |

Decide by **(a) which organisation produced the pixels**, **(b) whether ESA produced them and
where/when they were published**, and **(c) whether the product is an STScI-produced reduction**.
Record the reasoning in the file description. If genuinely ambiguous, that is a question for the
Upload Wizard or Commons help, not a guess.

### 4.4 The provenance record

One record per candidate, kept for the life of the project — it becomes the file description
(§9.2), so assemble it before processing:

- object designation(s) and all aliases; RA/Dec and equinox; distance with its source
- archive name, **the exact query or URL used**, and the retrieval date
- programme / observation ID, instrument, filter, exposure time, DATE-OBS; MAST DOI if available
- **data licence, verbatim**; and whether the FITS is raw, calibrated, or a pre-composited
  "science ready" product (§7.1)
- telescope, camera, filters, gain/binning if own data; total integration per channel
- the reference survey image used for orientation and star colour (§7.6)

The log is the raw material for the file description, so write it as you go. The MAST DOI is the
strongest single provenance anchor available for space-telescope data — STScI recommends citing
data and pipeline versions.

---

## 5. What colour are you actually making?

Decide per object, before any processing. Only the first two modes carry information.

| Mode | Needs | What the colour means | Commons position |
|---|---|---|---|
| **Broadband "true" colour** | R, G, B data (separate filters or one-shot colour camera) | approximately true colour | strongest; best for galaxies, clusters, reflection nebulae |
| **Narrowband false colour** | 2–3 narrowband sets (Hα, [O III], [S II]) | a *documented* wavelength→RGB mapping, not literal colour | standard **if the mapping is stated in the file description** |
| **Multi-filter IR representative colour** | 3+ IR filters (JWST NIRCam/MIRI) | a stated wavelength→visible mapping; **no literal human-visible colour exists** | acceptable if described accurately — "false-colour composite based on NIRCam observations in *n* infrared filters", never "the actual colour of the nebula" |
| **Grayscale** | one band, or no honest mapping available | none | **fully acceptable, and the correct default for single-band data** |
| **Single-band synthetic tint** | one band, tinted | nothing — aesthetic only | zero information; weak justification for mainspace |

Two things most people get wrong, and both matter for a scientific image. **"True colour" is
itself an approximation**: a monochrome sensor through B/V/R or U/V/B gives a *filtered*
approximation, the eye is far more sensitive in green so equal integration per channel goes
green-heavy, and filter widths and throughputs differ wildly — which is what photometric colour
calibration exists to fix. So **never label an image "true colour" unqualified**; call it a
"broadband RGB composite" and list the filters. And **two narrowbands beat a pretty single band**:
an [O III]-only image genuinely shows the distribution of a specific ion, whereas a tri-tone
gradient on a single Hα frame shows nothing except your taste.

| Object type | Default mode | Why |
|---|---|---|
| Galaxy, galaxy cluster, deep field | broadband RGB | colour carries real information (redshift, star formation) |
| Globular / open cluster | broadband RGB | stars are the subject; star colour *is* the science |
| Reflection nebula | broadband RGB | scattered light, roughly solar colours |
| Emission nebula (HII region) | SHO (Hubble palette) or HOO | line emission; false-colour standard, largest coverage gap |
| Planetary nebula | SHO or HOO | both work; HOO is legible |
| Supernova remnant | broadband, or [S II]/Hα for the shock | velocity gradient is the science |
| **Anything you have one band of** | **publish grayscale** | a tint implies colour information that is not there |

**Narrowband mapping is not a linear hue split.** [S II]→red, Hα→green, [O III]→blue is the
*label*, not the recipe: a straight one-third split produces muddy, unconvincing colour. Use a
proper sensitivity-transfer / non-linear hue mapping, and for HOO mix Hα toward green to reach the
familiar gold/teal. With broadband data available, blend a desaturated continuum layer beneath the
narrowband layer — that is what makes modern narrowband images credible rather than poster-like.
**Record the exact mapping**; it goes verbatim in the file description and it is what makes a
false-colour image acceptable.

**5.3 The IR niche.** Nearly all infrared colour imagery is auto-generated by a survey pipeline and
rarely reaches Commons in a reprocessed, documented form. The IR→visible mapping is a stated
convention, not a claim about appearance, which is what makes it defensible. Same logic applies to
raw deep-survey frames (DECam, NOIRLab deep drills) never given a public colour rendering.

---

## 6. Finding a target that is genuinely uncovered

### 6.1 Gap taxonomy

"Not yet colourised" is a symptom. The decision-relevant taxonomy:

| Gap | Description | How exploitable |
|---|---|---|
| **G0 — no image at all** | article or catalogue entry exists, zero images | most exploitable, slowest |
| **G1 — grayscale only** | a monochrome amateur or survey image, no colour version | literally "not yet colourised" — the direct answer to the question |
| **G2 — over-processed colour only** | a colour image exists with a rainbow/clipped look; no restrained version | high value; improvement is easy to demonstrate |
| **G3 — inferior or badly framed colour** | low resolution, badly cropped, wrong scale, missing the interesting part | moderate; you must argue yours is genuinely better |
| **G4 — low-resolution press/survey image only** | a 512px or 1k cutout, nothing better | very exploitable — a large fraction of the catalogue |

Strategic note on G4: the over-served era for Wikimedia astronomy was roughly 2005–2015. A great
many catalogue objects have not been re-imaged since, while the *well-known* objects are saturated
with Hubble/ESO/JWST press images. The underserved population is the long tail.

### 6.2 Method 1 — catalogue-driven coverage audit (primary)

Choose a catalogue by target type: Sharpless 2 (~310), RCW, Collinder, van den Bergh for HII
regions; NGC (~7840) and IC (~5400) for planetary nebulae and clusters; Abell, UGC, PGC, LEDA for
galaxies; Caldwell (a subset — skip the famous ones). **Batch the P18 check with SPARQL** (§1, 0.B)
rather than object by object, and **cross-identify before concluding anything** — SIMBAD, NED and
VizieR give the alias set, and a gap found under one designation may be covered under another. Then
per survivor: the English Wikipedia lead/infobox image (also non-English Wikipedias — a gap there is
still an opportunity), the Commons category for the designation (frequently incomplete, and it hides
files), and Commons full-text search on the designation *and* every alias. Classify the gap and
score it. Many NGC/IC "objects" are worthless — single stars, asterisms, duplicates, extremely faint
— so filter by size and brightness against a survey image early.

### 6.3 Method 2 — data-archive-first (most scalable, most overlooked)

The publisher of raw data very often does **not** publish a colour version. That asymmetry is the
opportunity. Check what data exists *before* looking at image galleries.

| Tool | What it answers |
|---|---|
| **SkyView (NASA HEASARC)** | is there usable data here, and what does the field look like — any coordinate, one query (SDSS, PS1, 2MASS, WISE, GALEX). The single most useful triage tool in the project. **Reference only, not a source** (§4.2). |
| **PS1 DR2 cutout service** | on-demand `gri`/`yzy` colour for arbitrary coordinates — coverage test *and* the reference image for orientation and star colour (§7.6) |
| **ESASky** | pan the sky; which HST/JWST/Chandra/ISO footprints exist |
| **SDSS SkyServer** | northern footprint, five-band calibrated photometry, colour-calibrated reference |
| **MAST** | Hubble, JWST, TESS, GALEX. **Filter by release date** for newly public data; accepts an uploaded target list; scriptable via `astroquery` |
| **Hubble Legacy Archive (hla.stsci.edu)** | quick-look previews — a preview existing does not mean a finished image exists |
| **ESO Archive**, **NOIRLab**, **IRSA** (Spitzer/WISE), **Chandra**, **DESI Legacy viewer** | further coverage; VLT instruments (FORS2, HAWK-I; MUSE is harder), the IR and deep-survey niches (§5.3) |
| **Zenodo**, **NASA ADS** | author deposits under explicit CC licences; and recent literature on a target — the evidence test below |

**Which product to download** — the difference between an executable plan and a research
prerequisite:

| Mission | Start at | Notes |
|---|---|---|
| **JWST** | Stage 2 `*_cal.fits` (per-exposure calibrated) or Stage 3 `*_i2d.fits` (combined) | Stage 0 `*_uncal.fits` is the closest thing to raw detector data and is rarely what you want; `*_rate.fits` is Stage 1. Stage 2/3 give essentially untouched scientific imaging without re-running the pipeline. |
| **Hubble** | `_drz.fits` (drizzled, combined) or `_drc.fits` | **`drc` is preferred for ACS/WFC3** — it has CTE correction. Drizzled data from the same visit is sometimes already aligned across filters. |
| **Own data** | calibrated frames | §7.2 |

**Timeliness as a discovery axis.** New observations pass through a **proprietary period** — roughly
12 months for ground-based facilities, and NASA describes a six-month proprietary period for Hubble
observations — after which the data is public but frequently never rendered as a picture. "Recently
public, never released as an image" is the sweet spot: the science is settled enough to be
uncontroversial and nobody has beaten you to it.

**The evidence test** for "the data exists and the colour version genuinely doesn't": find a recent
**ADS** paper about the object whose figure is monochrome. That one citation establishes the data,
the scientific interest, *and* the gap.

Keep one row per candidate — filters, existing colour image?, S/N, interesting?, licence/provenance,
score — so the shortlist is argued rather than accumulated.

### 6.4 Methods 3 and 4 — reverse audit, and timeliness

Browse a category of astronomical objects on Commons and look for **monochrome or over-saturated**
files: those are your upgrade candidates. Search for SHO/HOO composites **over-saturated to the
point of clipping a channel** — a restrained recomposite of the same data, from the same FITS, is
both easier to produce and more likely to be promoted than a new object. Check the QI/FP gaps: an
object with a mediocre colour image and no QI/FP is a good promotion candidate.

Real gaps also open around newly named interstellar objects, newly identified SNR candidates, objects
whose distance was substantially revised, JWST-observed targets not yet on Commons, and objects
where a recent discovery made an existing image irrelevant. Interest here is higher, so the file
actually gets used.

### 6.5 Scoring rubric

Score 0–3 per row. **A 0 on row 1 or row 2 drops the candidate immediately.**

| # | Criterion | Why it matters |
|---|---|---|
| 1 | **Data licence is clean and identified** | hard gate. No licence, no upload. |
| 2 | **A real coverage gap exists** (G0/G1/G4) | the whole point |
| 3 | **The object is notable enough for Commons** | a background galaxy in a large mosaic is out of scope however well processed. Does it have an article, or a catalogue entry editors would plausibly want illustrated? **The one screen no source plan had.** |
| 4 | **Data is high enough S/N to look good** | 3 = abundant, 1 = marginal |
| 5 | **Object type suits the colour mode available** | §5 |
| 6 | **No hard core** (M42, M31 core, M13, η Car) unless HDR-capable | clipped cores are the classic amateur failure |
| 7 | **Field of view suits the article** | a 0.5° frame of a 3° object may be worse than useless |
| 8 | **Orientation and star colour are verifiable** against a survey image | §7.6 |
| 9 | **Reachable with your equipment, or the data is archived** | feasibility |
| 10 | **Educational / informative value, not just prettiness** | what an article actually needs |

Keep the shortlist at 5–10. If two candidates tie, prefer the one with the simpler licence.

### 6.6 Where the odds are best

**Do not** compete with Hubble/ESO/JWST press releases for the famous ~200 objects — their images
are already on Commons, often already FP, and made by professionals. **Do** target zero coverage,
survey-cutout-only coverage, monochrome-only coverage, and objects where a **documented, restrained**
composite would be visibly better.

Space-archive data is the path of least resistance — clean licences, abundant multi-filter data,
ready-made products — but its photogenic objects are the ones the mission's own imagery team has
already published. Ground-based catalogue work hits a real gap but needs your own scope or an
archive that covers the object. **This trade-off is your first real decision** (§12 D1). And a
correctly-scaled, correctly-oriented, properly-labelled image of a *modest* object teaches a reader
more than a spectacular image of a famous one — much of the reward in Wikimedia review comes from
this.

---

## 7. The pipeline

**The order below is not a style preference. Each step is a precondition for the next being
correct.** Four rules between them prevent the most common rejection:

1. Establish and fix the data's **state** (linear vs already-stretched) before anything else.
2. Normalise channels **in linear space**, before any stretch.
3. Assign colour **before** the stretch.
4. Apply **one shared stretch** to all channels — same function, same parameters.

### 7.1 Establish the data's true state — the step people skip

**Linear (raw ADU) or already non-linearly stretched?** The histogram is the tell: linear data has a
narrow sky-background peak with a long faint tail; stretched data has a much flatter, wider
distribution. **Summed/averaged or pre-composited?** Some "science ready" products are already
composited — check HDU count, extension names, header keywords. **Mosaic?** Check
`HISTORY`/software keywords and the WCS footprint. Also record bit depth, pixel scale and gain.

**If the data is already stretched, linearisation is mandatory** — fit and invert the stretch
function (asinh/arcsinh with a known shadow-clip point, or whatever was used) to return to linear
space. Compositing stretched data gives wrong inter-channel ratios, therefore wrong colour, and no
amount of later curve work will fix it. This finding determines whether §7.3 is even possible.

### 7.2 Calibration (own raw data only)

Archive FITS is usually already calibrated (§6.3). For your own frames: bias, dark, flat and sky
frames; debayer for a one-shot colour camera; cosmic-ray rejection; register and integrate
subframes (plate-solve with astrometry.net or trust the header WCS); mosaic if multi-panel, with
**panels photometrically matched or the seam will show**; gradient and vignette handling.

### 7.3 Linear channel normalisation

Still in linear space: subtract the background per channel; normalise channels so their **sky
backgrounds match** — the correct anchor; correct for **filter throughput** differences; **colour
calibrate** (for narrowband, photometric calibration in the SPCC style pinning the field's colour to
a reference — without it the "gold" look is guesswork); detect and **mask saturated pixels** (bright
cores, star centres) so they cannot drive the stretch; deconvolve only with care, since it sharpens
noise and creates ringing.

### 7.4 Colour assignment

Where the channels are combined — **before the stretch**. Broadband R→R/G→G/B→B after
normalisation is the honest default; narrowband and IR mappings per §5. With more than three
filters, give each its own hue and blend, in wavelength order. With two, synthesise green as their
average. **Record the exact mapping** — it is what makes a false-colour image acceptable.

### 7.5 One stretch, applied correctly

- **The same function and the same parameters to every channel.** Independent per-channel
  stretching is the number-one cause of "unnatural colours" in review comments.
- **asinh / arcsinh** or generalised hyperbolic (GHS) with a **defined, recorded shadow-clip
  point**. The SC value is the single most impactful parameter: it sets how much faint signal you
  are willing to lift, and therefore how the object reads.
- A histogram transformation or complementary curve step is a reasonable addition.
- Land the background on a **defined, recorded level**, so the result is reproducible and a reviewer
  can tell what you did.
- **The practical test of correct colour is the stars** — §7.6.
- **Fork here.** Export the data version (§3.2) before any of §7.7.

### 7.6 Orientation and star colour verification

The highest-value, lowest-cost step in the pipeline, and the one that separates a competent image
from a rejected one. It is a **verification** step, not a caption field.

- **Orientation:** pull a PS1 or SDSS colour image of the same field and match rotation and
  handedness. A mosaic from a camera with no 180° rotator is very often **180° rotated**; an image
  published upside-down or mirrored is an immediate, visible reject, and the same check catches
  field-of-view mistakes.
- **Star colour:** find a colour-calibrated reference of the same field. Blue-white stars must read
  blue-white; orange giants must read orange. A pure SHO composite gives every star identical
  colour, which is the single biggest visual tell of amateur processing. Where you have both
  broadband and narrowband, **use the broadband RGB image of the same field as the star-colour
  reference** and blend it into the stars.

### 7.7 Post-processing — the presentation version only

In order, conservatively: noise reduction (TGV / multiscale, applied lightly; over-reduction reads
as plastic); star reduction, if any — must not damage the field, and must be disclosed; halo/bloom
reduction; **chromatic aberration correction** — explicitly a listed defect in the Commons image
guidelines ("typically purple hazing at contrast edges"), common with fast newt lenses; background
gradient and residual flat-field cleanup; local contrast and careful sharpening, watching for
ringing halos; saturation — raise it, but oversaturation is a listed defect and QI requires
"reasonable colours", so the neon rainbow nebula look is a rejection, not a feature; and **HDR /
exposure blending for hard cores** — required for M42, M31's core, M13, η Car.

### 7.8 Check for banding

Faint gradients band badly after a strong stretch, especially after 8-bit JPEG. Check at 100% in
the faint outskirts. Mitigate with 16-bit intermediates, dithering, and a small amount of retained
noise. Keep a **16-bit TIFF master**; upload PNG, or high-quality JPEG for very large files, at full
resolution.

### 7.9 Produce the audit trail — while working, not afterwards

Keep the FITS, the project files, and a **step-by-step log with parameters** (template §13.2). The
log is the raw material for the file description, and if you intend to claim a reproducible result,
the log plus the public data must let someone else rebuild it.

**On reproducibility and tooling:** a GUI session (Siril, GIMP, CARTA, DS9) is not reproducible by
a third party. That is a real tension with the justification this project rests on. Either commit
to a scripted chain — `astropy` + `reproject` + NumPy is sufficient for
load → normalise → align → stretch → map → composite, and MAST is scriptable via `astroquery` — or
stop claiming reproducibility as the reason the work is valuable. The bar is the result and its
documentation, but the claim should be one you can keep.

---

## 8. Definition of done

Publishable only when **all** of these hold:

- [ ] sRGB colour space, correctly tagged; embedded ICC profile
- [ ] no clipped star cores (or documented HDR handling of the clipped ones)
- [ ] no chromatic aberration fringing
- [ ] stars show plausible, varied colour
- [ ] background at a consistent level; no visible gradient, no banding
- [ ] no visible seams or hue jumps in a mosaic
- [ ] **orientation and field of view verified against a survey image**
- [ ] noise visible at 100% but not blotchy; not plastic
- [ ] not oversaturated; no channel clipping in the nebula
- [ ] the false-colour mapping is written down and reproducible
- [ ] the whole chain is reproducible from the published data
- [ ] provenance and data licence recorded

Two optional but valuable additions: a **small grayscale or linear-scale reference** — or the data
version (§3.2) — linked from the file page, so a reviewer can see the unprocessed data; and an
orientation/FOV statement. Some reviewers find in-image annotation distracting, so the safer minimum
is a precise caption plus a note on the talk page.

---

## 9. Packaging and publishing

Hosting on Commons is the easy half. Being *used* is the deliverable.

**9.1 Naming.** Astronomy convention: `Object designation (palette/instrument, year).jpg` — e.g.
`Sh2-155 (HOO, 20" Newtonian, 2026).jpg`. Check recent Commons astronomy files for current practice.

**9.2 The file description — where the work is judged.** Minimum viable set: object (primary
designation, common name, all aliases); type; RA/Dec and equinox; distance and *how* you got it
(redshift, association, literature reference); field of view and orientation (N up / E left, or as
stated); data source (archive or own equipment, exact query/URL or programme ID, dataset IDs, MAST
DOI if available, retrieval date); data licence and the licence of the composite, with the §4.3
reasoning; instrument and acquisition (telescope/optic, camera, filters, exposure per channel, gain,
binning, integration total, date); processing (software and versions, calibration,
registration/integration method, stretch function and shadow-clip value, colour mapping,
denoise/sharpen/saturation steps); author and co-authors; attribution to the data provider with the
required credit statement (ESO requires a specific form); and a link to the data version (§3.2). Use
`{{Information}}` with an appropriate source tag plus the provider's credit, check whether a
facility-specific template exists, and disclose manipulation with `{{Retouched}}` where processing
goes beyond ordinary correction. **Never use `{{PD-Hubble}}` or `{{PD-Webb}}` without having
applied §4.3.**

**9.3 Categories and structured data.** The specific object, its type, its constellation;
"Astronomical images by \<author\>"; palette-specific categories if they exist (SHO / Hubble
palette / HOO); and **Structured Data "Depicts"** — it drives Commons search and is badly underused.

**9.4 Upload, in order.** (1) `commons.wikimedia.org → Upload file`. (2) Fill the description
fields from §9.2, with the author line as "NASA/ESA/CSA/STScI (data); processed by \<you\>" plus
your own-work statement. (3) Licence template per §4.3 — not per assumption. (4) Categories and
Structured Data. (5) Link it: the **Wikidata item (P18)** and the article infobox; if the object has
no article, the Wikidata link alone still helps. (6) Check the licence and one unrelated checkbox on
the upload summary before publishing — most deletions happen at this step, not at review. (7)
Nominate for QI only after §8 passes in full.

**9.5 Getting it *used*.** Add it to the relevant articles: the lead image is chosen for
**informativeness**, so a tight, well-exposed, correctly-scaled image beats a sprawling spectacular
one. A good NGC/IC/Abell image is typically wanted by **many language Wikipedias** — the
highest-leverage step in the publishing phase, and routinely forgotten. Then the relevant
WikiProjects (Astronomy, Physics) and astronomy template galleries, and a decision about whether the
best home is an infobox, a gallery section, or a comparison table. Keep the description precise
enough that a volunteer editor can verify it and adopt it.

**9.6 Wikipedia-side cautions.** The caption must not assert novel scientific findings — describe
what the image shows. The method and data source must be verifiable, which is what keeps this out of
original-research territory. The file must be freely licensed and hosted on Commons to be usable at
all. False colour must be declared in the caption wherever it is material.

---

## 10. Review and promotion

**Read the bar before the long processing session, not after.** Recurring points from the Commons
image and QI/FP guidelines: technical quality, with "wow factor" for FP and a Commons user as author
for QI; **oversaturation is a defect** and QI requires "reasonable colours" and not too bright;
**noise is a defect** and grounds for opposition; **chromatic aberration** and **inappropriate
colour space** are listed defects; **burned highlights** are distracting; manipulation must not
deceive and extensive manipulation must be described; sRGB is required and untagged non-sRGB is a
defect. And the process itself: **FPC needs a 9-day voting period, 7 supports minimum, 2:1 ratio;
10 supports with no opposition promotes early; two active nominations per user maximum.**

**Sets are an option, with a caveat.** Commons accepts set nominations and there is recent astronomy
precedent — a multiband palette study of M42 was promoted as an FP set, pixel-aligned for blink
comparison. The accepted rationale was "different band combinations of the same subject"; "you can
show 50 colours" is a rejection waiting to happen. A small, purposeful, ordered set with a stated
logic is worth attempting **once the single-image workflow is solid** — which is an argument for
not making a six-hue rainbow your first upload.

**Route:** Quality Image first (lower bar, faster cycle, still a real assessment), then Featured
Picture. Expect the first FP attempt to be opposed; read the opposition carefully, it is usually one
specific fixable technical point. Keep the linear data and project files so a revision is cheap, and
remember FP/QI files may not be overwritten — settle the technical state first.

---

## 11. Tools

| Stage | Free and capable | Paid |
|---|---|---|
| Acquisition (own data) | N.I.N.A., Siril, Astro Pixel Processor (APP), KStars/EkOS, ASCOM | — |
| Calibration / registration / integration / deconvolution | Siril, APP | PixInsight (incl. RC-Astro) |
| Photometric colour calibration, DBE | Siril has equivalents | PixInsight (SPCC, DBE) |
| Inspection / FITS colour viewing / plate solving | **SAOImage DS9**, **Aladin**, **CARTA** (ESA); astrometry.net or header WCS | — |
| Survey colour reference | SkyView, PS1 cutout service, SDSS SkyServer | — |
| Stretch / convert FITS | **FITS Liberator** (ESA/NOIRLab), Siril | PixInsight |
| Final pixel work | GIMP, Krita | Photoshop, Affinity |
| Scripted / reproducible route | **Python: astropy + reproject + NumPy**; `astroquery` for MAST | — |

Siril, APP, CARTA, Aladin, DS9, FITS Liberator and GIMP are free and entirely capable. PixInsight
is commercial and the de facto standard for work aiming at Featured status — its WBPP, SPCC and GHS
are the shortest route to the §8 bar. For a first project the choice does not matter; for QI/FP it
does. Documentation is a structured log (§13.2), not a tool.

---

## 12. Open decisions

Take these in order; each changes the work that follows. None is resolved by this document.

1. **D1 — own telescope, ground-based catalogue sweep, or space-archive data.** Determines the
   rights strategy, the equipment, the target list and the competitive framing (§6.6).
2. **D3 — is a reproducible scripted chain a requirement or a nicety?** If a requirement, the
   GUI-first path contradicts the project's own justification (§7.9).
3. **D2 — is a multi-palette set the first deliverable or a later one?** It decides whether the risk
   profile starts high or is built up (§10).
4. **Own data vs. archive data.** Archive-only is faster and cleaner on rights; own data is the
   stronger long-term position and the easiest provenance story.
5. **Is a beginner-facing summary a required deliverable?** Entry point 0.C is not served by a
   document written at this level.
6. **Is the batch (SPARQL) coverage audit step one?** If adopted, the shortlist is *generated*, not
   hand-picked, and the §6.5 rubric scores its output.
7. **Object class, geography, time budget per image.** Realistic figures: 10–20 h for a first
   archive-data narrowband composite done properly, more for mosaics and HDR. Emission nebulae are
   the most forgiving and have the largest coverage gap; galaxies give the most scientific value per
   image and are the most unforgiving on colour.

---

## 13. Templates

### 13.1 Target dossier (one per candidate)

```
Object:            <designation> (<common name>)   Aliases: <every designation, from SIMBAD/NED>
Type:              <emission nebula / galaxy/...> RA/Dec (equinox): <coords>   FOV / scale: <...>
Distance:          <value> — <source>             Notable? <article/catalogue entry; why an editor wants it>
Gap type:          G0 / G1 / G2 / G3 / G4   <evidence, with URLs>
Colour mode:       broadband RGB / SHO / HOO / IR mapping / grayscale
Data source:       <archive> — <query or URL> — retrieved <date>
Obs ID:            <programme / observation id>  MAST DOI: <...>   Data licence: <verbatim>
Product level:     raw / calibrated / i2d / drz / drc / already stretched?
Channels:          <filter: exp, count, total integration>
Reference image:   <PS1/SDSS URL for orientation + star colour>
Score:             <§6.5 rubric, out of 30>      Verdict: pursue / hold / drop
```

### 13.2 Processing log (one per produced image)

```
Software + versions:            Date processed:            Operator:

 1. Source data (archive/own, ID, retrieval date, licence)
 2. Calibration applied (or: data already calibrated)
 3. State check: linear / already-stretched / composited / mosaic -> action taken
 4. Registration + integration (method, dither, alignment)   5. Linearisation (required? method, params)
 6. Background subtraction + channel normalisation (method, values)
 7. Colour calibration (method, reference, result)          8. Saturated-pixel handling
 9. Colour mapping (exact channel -> colour, incl. any non-linear mapping)
10. Stretch (function, shadow clip, iterations, shared across channels: yes/no)
11. Background level set to
12. Reference check: survey image for orientation (URL); rotation applied
13. Star colour check: reference used; result
14. Star reduction / denoise (methods, strengths)           15. Chromatic aberration correction
16. HDR / exposure blending (if used)                       17. Gradients, sharpening, saturation
18. Output colour space, bit depth, banding check
19. Data version exported (path) — presentation version exported (path)
20. Archive path for FITS + project files
21. Licence tag chosen, with the §4.3 reasoning
```

---

## 14. Checklists

**14.1 Smallest viable first upload (entry point 0.C — start here).** Pick a famous object that
already has an excellent Commons colour image; reprocess the same public FITS and compare side by
side. Nothing to lose. One filter or a 2–3 filter set (one filter ⇒ grayscale, §5). Confirm the
data licence in the FITS header and against §4.2 — **DSS is not free to reuse**. Linearise if
needed → normalise → colour → **one shared stretch** → light post. Verify orientation and star
colour against a PS1/SDSS reference. Work through §8, then §9. Then take a real 0.A or 0.B target
and repeat.

**14.2 Pre-flight — may I proceed?**

- [ ] Data is public, and any proprietary period is over
- [ ] Data licence is free — **not DSS**, not non-commercial, not "research use only"
- [ ] §4.3 applied: correct licence tag identified, with reasoning recorded
- [ ] No good existing image on Wikidata (P18), Commons, official galleries, or community sites
- [ ] The object is notable enough for Commons (§6.5 row 3)
- [ ] Two or more filters — or a deliberate, honest grayscale
- [ ] Orientation and star colour are verifiable against a survey image
- [ ] Colour mode chosen and its mapping written down; processing log open

**14.3 Post-processing and upload — is it finished, and is it safely published?**

- [ ] §8, all twelve items; banding checked at 100% in the faint outskirts
- [ ] Data version exported and archived; 16-bit master retained; processing log complete (§13.2)
- [ ] Filename per §9.1; all §9.2 description fields present, including colour mapping and licence
- [ ] Licence tag correct per §4.3; credit statement in the provider's required form
- [ ] `{{Retouched}}` / manipulation disclosure added if applicable
- [ ] Categories and Structured Data "Depicts" filled
- [ ] Wikidata P18 set; article infobox updated
- [ ] Licence and one unrelated checkbox verified on the upload summary
- [ ] Only then: QI nomination (§10)

---

## 15. Sources to re-check at execution time

Verified as of 2026-09-26 where dated above. These drift — re-read before the first upload and
before any promotion attempt:

- Guidelines: `Commons:Image_guidelines`, `Commons:Featured_picture_candidates/guidelines`,
  `Commons:Quality_images/guidelines`, `Commons:Upscaling`, `Commons:AI-generated_media`, and the
  open AI policy RfC on `meta.wikimedia.org`
- Licence templates themselves: `{{PD-Hubble}}`, `{{ESA-Hubble}}`, `{{PD-Webb}}`, `{{ESA-Webb}}`,
  `{{PD-USGov-NASA}}`
- Data-access policies: ESO, NOIRLab, MAST/Hubble, any survey cutout service used, and
  `archive.stsci.edu/dss/copyright.html` — plus the copyright line in each FITS header
- The article categories and templates in use at upload time
