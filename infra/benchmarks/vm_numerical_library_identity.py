"""Identify the actual numerical shared libraries; no installations or model execution."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
signal.alarm(15)
start = time.perf_counter()
import numpy as np
np.linalg.eigh(np.eye(4))
paths = sorted({line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()
                if any(s in line.lower() for s in ("blas", "lapack", "mkl", "libgomp", "libomp")) and "/" in line})
libraries = []
for item in paths:
    path = Path(item)
    libraries.append({"path": item, "resolved": str(path.resolve()),
                      "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
report = {"kind": "NUMERICAL_LIBRARY_IDENTITY_ONLY", "source_commit": sys.argv[1],
          "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "numpy": np.__version__, "loaded_libraries": libraries,
          "process_threads": next(line for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("Threads:")),
          "thread_environment": {key: os.environ.get(key) for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
          "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
          "wall_s": time.perf_counter()-start}
Path("LIBRARIES.json").write_text(json.dumps(report, indent=2)+"\n")
print(json.dumps(report))
