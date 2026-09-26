"""Fetch a real pointed dataset for the pipeline to be tested on (plan §4.4, §6.3, §13.1).

Why a script and not `astroquery.mast.download_products`: on 2026-09-26 the live MAST
*observations* service answered every query, and the *product* service answered none of them —
`Observations.get_product_list` fails for every HST and JWST observation with
`RemoteServiceError: Error converting data type varchar to bigint`, a server-side fault. The
Download service itself is healthy, and the per-visit drizzle products follow a fixed naming
convention, so the URI is constructed instead of looked up:

	mast:HST/product/<obsid>/<obsid>_drc.fits     preferred for ACS/WFC3 (CTE correction)
	mast:HST/product/<obsid>/<obsid>_drz.fits     per-visit drizzled combined
	mast:HST/product/<obsid>/<obsid>_o<nnn>_drz.fits   multi-visit drizzled combined

Each candidate is probed with a one-byte range request, so a missing product costs 41 bytes
rather than a 404 page. Downloads resume with an HTTP Range and are skipped when the file
already has the size the server reports, which matters because a session can end mid-transfer.
Every file is recorded in `manifest.csv` with the observation metadata, the byte count, a
sha256 and the retrieval time — the §4.4 provenance record the dossier and the upload
description both need, written down before processing rather than reconstructed afterwards.

	experiments/fetch_data.py SH2-252F --obsid ichx02020 ichx02030 ichx02040
"""

import argparse
import csv
import hashlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from astroproc.audit.http import request  # noqa: E402

DOWNLOAD = "https://mast.stsci.edu/api/v0.1/Download/file"
CHUNK = 1 << 20
# `_drc` first: plan §6.3 prefers it for ACS/WFC3 because it carries the CTE correction.
SUFFIXES = ("_drc.fits", "_drz.fits")
MANIFEST = ("target", "obsid", "instrument", "filter", "exptime_s", "proposal", "product",
	"bytes", "sha256", "retrieved_utc", "uri")


def product_uri(obsid, suffix):
	return f"mast:HST/product/{obsid}/{obsid}{suffix}"


def remote_size(uri):
	"""Size the server reports for a product, or None when it does not exist."""
	try:
		response = request("GET", DOWNLOAD, timeout=60, params={"uri": uri}, headers={
			"Request-Method": "GET", "Range": "bytes=0-0"})
	except Exception as exc:
		print(f"  probe failed: {type(exc).__name__}: {exc}")
		return None
	if response.status_code not in (200, 206):
		return None
	span = response.headers.get("Content-Range", "")
	return int(span.rsplit("/", 1)[1]) if "/" in span else len(response.content)


def find_product(obsid):
	"""First existing drizzle product for one observation, with its size."""
	for suffix in SUFFIXES:
		uri = product_uri(obsid, suffix)
		size = remote_size(uri)
		if size:
			return uri, size
		print(f"  {obsid}{suffix}: absent")
	return None, None


def download(uri, path, expected):
	"""Fetch one product, resuming a partial file; True when the file is complete."""
	if path.exists() and path.stat().st_size == expected:
		print(f"  {path.name}: already complete ({expected} bytes)")
		return True
	have = path.stat().st_size if path.exists() else 0
	if have > expected:
		path.unlink()
		have = 0
	headers = {"Request-Method": "GET"}
	if have:
		headers["Range"] = f"bytes={have}-"
	with path.open("ab" if have else "wb") as handle:
		response = request("GET", DOWNLOAD, timeout=600, params={"uri": uri}, headers=headers, stream=True)
		for block in response.iter_content(CHUNK):
			handle.write(block)
			print(f"\r  {path.name}: {handle.tell() / 1e6:7.1f} / {expected / 1e6:.1f} MB", end="", flush=True)
	print()
	return path.stat().st_size == expected


# Header keys that carry the §4.4 provenance, in the order they are trusted.
HEADER_KEYS = {
	"instrument": ("INSTRUME", "INSTRUMENT"),
	"filter": ("FILTER", "FILTER1", "FILTER2"),
	"exptime_s": ("EXPTIME",),
	"proposal": ("PROPOSID", "PROPOSAL", "PROPOSAL ID"),
	"target": ("TARGNAME", "TARG_NAME", "OBJECT"),
	"ra": ("RA_TARG", "RA"),
	"dec": ("DEC_TARG", "DEC"),
}


def header_metadata(path):
	"""Provenance from the file itself.

	Not a fallback for convenience: the header is the record that travels with the data, so it
	is the one the upload description can be checked against. The MAST metadata service cannot
	be asked instead — on 2026-09-26 `Observations.query_criteria(obsid=...)` failed with the
	same `varchar to bigint` server error as the product listing, while the cone search worked.
	"""
	from astropy.io import fits

	out = {}
	with fits.open(path) as hdul:
		head = hdul[0].header
		for field, keys in HEADER_KEYS.items():
			value = next((head[key] for key in keys if key in head), None)
			if value is not None:
				out[field] = value
	return out


def sha256(path):
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for block in iter(lambda: handle.read(CHUNK), b""):
			digest.update(block)
	return digest.hexdigest()


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("target", help="directory name under data/")
	parser.add_argument("--obsid", nargs="+", required=True, help="observation ids to fetch")
	parser.add_argument("--data-dir", default=str(HERE.parent / "data"))
	args = parser.parse_args()

	directory = Path(args.data_dir) / args.target.replace(" ", "")
	directory.mkdir(parents=True, exist_ok=True)
	retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
	rows = []
	for obsid in args.obsid:
		uri, size = find_product(obsid)
		if not uri:
			print(f"{obsid}: no drizzle product found")
			continue
		path = directory / uri.rsplit("/", 1)[1]
		print(f"{obsid}: {path.name}, {size / 1e6:.1f} MB")
		if not download(uri, path, size):
			print(f"{obsid}: incomplete, will resume next run")
			continue
		rows.append({"obsid": obsid, "product": path.name, "bytes": size,
			"sha256": sha256(path), "retrieved_utc": retrieved, "uri": uri,
			"target": args.target, **header_metadata(path)})

	with (directory / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=list(MANIFEST), extrasaction="ignore")
		writer.writeheader()
		writer.writerows(rows)
	print(f"\n{len(rows)}/{len(args.obsid)} product(s) in {directory}")
	start = time.time()
	print(f"elapsed {time.time() - start:.0f}s")


if __name__ == "__main__":
	main()
