"""Hot-path measurement (AGENTS.md: avoid allocations in the hot path).

Times the shared asinh stretch on a 4k x 3-channel composite and reports the
allocations it makes. The stretch should cost one scratch buffer and O(N) ufunc work.
"""

import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from astroproc.stretch import StretchParams, asinh_stretch, auto_params  # noqa: E402

SIZE = 4096


def main():
	rng = np.random.default_rng(1)
	x = (rng.normal(120.0, 8.0, (3, SIZE, SIZE)) + 5000.0 * (rng.random((SIZE, SIZE)) < 1e-4)).astype(np.float32)
	params = auto_params(x)

	# timing first: tracemalloc instruments every allocation and skews wall time
	t0 = time.perf_counter()
	y, shift = asinh_stretch(x, params)
	elapsed = time.perf_counter() - t0

	tracemalloc.start()
	y2, _ = asinh_stretch(x, params)
	_, peak = tracemalloc.get_traced_memory()
	tracemalloc.stop()
	assert np.array_equal(y, y2)

	pixels = 3 * SIZE * SIZE
	mps = pixels / elapsed / 1e6
	lines = [
		f"input: {x.shape} float32 ({x.nbytes / 1e6:.0f} MB)",
		f"stretch wall time: {elapsed * 1e3:.0f} ms",
		f"throughput: {mps:.0f} Mpixel/s",
		f"peak traced allocation beyond input: {peak / 1e6:.0f} MB "
		f"(one float32 scratch of {x.nbytes / 1e6:.0f} MB is expected)",
		f"background shift applied: {shift:+.4f}",
		f"output dtype: {y.dtype}, range [{y.min():.4f}, {y.max():.4f}]",
	]
	report = "\n".join(lines)
	print(report)
	return report


if __name__ == "__main__":
	report = main()
	log = HERE / "logs" / "stretch_perf.log"
	log.parent.mkdir(exist_ok=True)
	with log.open("a", encoding="utf-8", newline="\n") as fh:
		fh.write(report + "\n\n")
