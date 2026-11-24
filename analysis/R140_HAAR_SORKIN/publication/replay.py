"""Verify the distributed files and rerun the published R136 and R140 calculations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R136 = ROOT / "analysis/R136_SHIROGANE_CALIBRATION"
R140 = ROOT / "analysis/R140_HAAR_SORKIN"
ENV = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "MPLBACKEND": "Agg", "PYTHONDONTWRITEBYTECODE": "1"}


def run(script, *args):
    return subprocess.check_output([sys.executable, str(script), *map(str, args)], cwd=ROOT, env=ENV)


def require_equal(label, actual, expected):
    if actual != expected:
        raise ValueError(f"Replay differs from the published file: {label}")


def check_inventory():
    lines = (ROOT / "MANIFEST.sha256").read_text().splitlines()
    for line in lines:
        expected, name = line.split("  ", 1)
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        require_equal(name, actual, expected)
    print(f"PASS: {len(lines)} SHA-256 digests")


def replay_local(work):
    for script, args in [
        (R136 / "verify.py", ["--check"]),
        (R136 / "test_gls_contrast_units.py", []),
        (R136 / "audit_invariant_D.py", []),
    ]:
        run(script, *args)
    require_equal("method-volume data", json.loads(run(R136 / "audit_method_volume.py")),
                  json.loads((R136 / "METHOD_VOLUME.json").read_bytes()))
    peer = R140 / "peer_audit"
    require_equal("integer history audit", json.loads(run(peer / "verify.py", "--endpoints-only"))["endpoints"],
                  json.loads((peer / "CHECKS.json").read_bytes())["endpoints"])
    print("PASS: R136 calibration, GLS and method contrast; R140 exact endpoint audit")


def replay_dynamics(work, checkout):
    # Isolate four already-published imports and check their exact bytes before running them.
    engine = work / "model"
    runtime = engine / "analysis/R140_HAAR_SORKIN"
    (runtime / "peer_audit").mkdir(parents=True)
    for name in ["verify.py", "HISTORIES.json", "peer_audit/verify.py"]:
        shutil.copyfile(R140 / name, runtime / name)
    for row in json.loads((HERE / "DONOR_SOURCES.json").read_text()):
        dest = engine / row["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if checkout:
            shutil.copyfile(checkout / row["path"], dest)
        else:
            with urlopen(row["url"], timeout=90) as response, dest.open("wb") as local:
                shutil.copyfileobj(response, local)
        require_equal(row["path"], hashlib.sha256(dest.read_bytes()).hexdigest(), row["sha256"])
    histories = work / "histories.json"
    require_equal("R140 primary checks", run(runtime / "verify.py", "--histories", histories),
                  (R140 / "CHECKS.json").read_bytes())
    require_equal("92 histories", histories.read_bytes(), (R140 / "HISTORIES.json").read_bytes())
    peer = R140 / "peer_audit"
    require_equal("R140 peer audit", run(runtime / "peer_audit/verify.py"), (peer / "CHECKS.json").read_bytes())
    print("PASS: R140 full dynamics, 92 histories, angles, records and refinement")


def replay_primary(work, source_dir):
    spec = json.loads((HERE / "PRIMARY_SOURCES.json").read_text())
    inputs = work / "primary"
    inputs.mkdir()
    for source in spec:
        dest = inputs / source["file"]
        if source_dir:
            shutil.copyfile(source_dir / dest.name, dest)
        else:
            with urlopen(source["url"], timeout=90) as response, dest.open("wb") as local:
                shutil.copyfileobj(response, local)
        require_equal(dest.name, hashlib.sha256(dest.read_bytes()).hexdigest(), source["sha256"])
    newer, older, pdf = (inputs / name for name in ("2021.tar", "2016.tar", "source.pdf"))
    require_equal("EPS extraction", run(R136 / "extract.py", newer, older), (R136 / "FIGURES.json").read_bytes())
    budget, plot = work / "budget.json", work / "map.svg"
    run(R136 / "audit_statistical_budget.py", newer, older, "--output", budget, "--plot", plot)
    require_equal("statistical budget", json.loads(budget.read_bytes()),
                  json.loads((R136 / "STATISTICAL_BUDGET.json").read_bytes()))
    require_equal("correlation map", plot.read_bytes(), (R136 / "CORRELATION_MAP.svg").read_bytes())
    historical = R136 / "archived_peer_audit"
    output = work / "archived-replay"
    run(historical / "audit.py", R136, newer, older, pdf, output)
    require_equal("archived audit", json.loads((output / "results.json").read_bytes()),
                  json.loads((historical / "results.json").read_bytes()))
    for name in ("fig3_flow.csv", "covariance_grid.csv"):
        require_equal(name, (output / name).read_bytes(), (historical / name).read_bytes())
    print("PASS: six source EPS files, correlation budget and SVG, archived PDF audit and both CSV tables")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--fetch-sources", action="store_true", help="Download the three pinned arXiv inputs.")
    options.add_argument("--source-dir", type=Path, help="Read 2021.tar, 2016.tar, source.pdf from this directory.")
    parser.add_argument("--donor-checkout", type=Path, help="Use the pinned donor files from a local vm-lab checkout.")
    args = parser.parse_args()
    check_inventory()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        replay_local(work)
        if args.fetch_sources or args.donor_checkout is not None:
            replay_dynamics(work, args.donor_checkout)
        if args.fetch_sources or args.source_dir is not None:
            replay_primary(work, args.source_dir)
