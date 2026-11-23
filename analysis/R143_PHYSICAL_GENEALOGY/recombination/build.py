#!/usr/bin/env python3
"""Build pinned R143 recombination dependencies; do not run a thermal history.

Requires git, make, gfortran and gcc already on PATH. No system packages are
installed. Work products stay below the explicitly supplied --work-dir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

CAMB_URL = "https://github.com/cmbant/CAMB.git"
CAMB_SHA = "53c1f1c0208f75223cf3da2b163187deb7310f42"
FORUTILS_SHA = "841f06d5356877e90437f94b2d976dd98f7f923c"
HYREC_URL = "https://github.com/nanoomlee/HYREC-2.git"
HYREC_SHA = "038dc8d71baed5c30a4fdd55576b97637ba5b879"
RECFAST_BASE_SHA256 = "14363a425b2352f837e1d353b885ebdfac5430f31517525ed6e75412269159f5"
RECFAST_FINE_SHA256 = "244ae6949898f0917e543c220655eff279aeb8e5f2838e51a8f685e53b27b9c9"
PATCH_SHA256 = "dc4b7c41c1cc7f4a716d61041ba7c034f387da82bae555f6a0bba2ef1d74ecc0"
HYREC_ADAPTER_SHA256 = "d14c62d773b62eeafcbdf066261465eee38286cf757408431051daf05aee9d34"
HYREC_SOURCES = ["hyrectools.c", "helium.c", "hydrogen.c", "history.c", "energy_injection.c"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_hash(path: Path, expected: str):
    if not path.is_file():
        raise RuntimeError(f"Required file is missing: {path}")
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"Checksum mismatch for {path}: {actual}; expected {expected}")


def run(*args, cwd=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def output(*args, cwd=None) -> str:
    return subprocess.check_output([str(arg) for arg in args], cwd=cwd, text=True).strip()


def checkout(url: str, commit: str, destination: Path):
    if not destination.exists():
        destination.mkdir(parents=True)
        run("git", "init", destination)
        run("git", "remote", "add", "origin", url, cwd=destination)
        run("git", "fetch", "--depth", "1", "origin", commit, cwd=destination)
        run("git", "checkout", "--detach", commit, cwd=destination)
    if not (destination / ".git").exists():
        raise RuntimeError(f"Existing destination is not a checkout: {destination}")
    if output("git", "rev-parse", "HEAD", cwd=destination) != commit:
        raise RuntimeError(f"Existing checkout is not pinned to {commit}: {destination}")
    if output("git", "remote", "get-url", "origin", cwd=destination) != url:
        raise RuntimeError(f"Existing checkout has a different origin: {destination}")


def prepare_camb(source: Path, patch: Path):
    checkout(CAMB_URL, CAMB_SHA, source)
    changed = output("git", "diff", "HEAD", "--name-only", cwd=source).splitlines()
    if changed:
        # A previous invocation may have left precisely our known fine source.
        # Reverse only that verified patch; never reset other local edits.
        if changed != ["fortran/recfast.f90"]:
            raise RuntimeError("CAMB contains unrelated tracked edits; use a fresh work directory")
        require_hash(source / "fortran/recfast.f90", RECFAST_FINE_SHA256)
        run("git", "apply", "--reverse", "--check", patch, cwd=source)
        run("git", "apply", "--reverse", patch, cwd=source)
    require_hash(source / "fortran/recfast.f90", RECFAST_BASE_SHA256)
    run("git", "submodule", "update", "--init", "forutils", cwd=source)
    if output("git", "rev-parse", "HEAD", cwd=source / "forutils") != FORUTILS_SHA:
        raise RuntimeError("Unexpected forutils commit")
    if output("git", "diff", "HEAD", "--name-only", cwd=source / "forutils"):
        raise RuntimeError("forutils has tracked edits; refusing to compile them")


def save_camb_package(source: Path, destination: Path, *, fine: bool, compiler: str, patch: Path):
    package = destination / "camb"
    shutil.copytree(source / "camb", package, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    # Source checkouts keep this import-time template outside the Python package.
    shutil.copy2(source / "fortran/HighLExtrapTemplate_lenspotentialCls.dat", package)
    profile = {
        "profile": "source_refined" if fine else "source_baseline",
        "CAMB_sha": CAMB_SHA,
        "forutils_sha": FORUTILS_SHA,
        "compiler": compiler,
        "build_command": "make -C fortran python CLUSTER_SAFE=1 COMPILER=gfortran -j1",
        "numerical_changes": [
            "Nz=20000 (delta_z=0.5)",
            "DVERK tolerance=1e-6",
            "Multiply all five cubic-spline curvature terms by delta_z**2 (unity for the stock grid)",
        ] if fine else [],
        "RECFAST_Nz": 20000 if fine else 10000,
        "RECFAST_delta_z": 0.5 if fine else 1.0,
        "RECFAST_DVERK_tolerance": 1e-6 if fine else 1e-5,
        "recfast_source_sha256": sha256(source / "fortran/recfast.f90"),
        "library_sha256": sha256(package / "camblib.so"),
    }
    if fine:
        profile["patch_sha256"] = sha256(patch)
    (package / "R143_BUILD.json").write_text(json.dumps(profile, indent=2) + "\n")
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True,
                        help="Directory for pinned source checkouts and compiled dependencies")
    parser.add_argument("--package-dir", type=Path, required=True,
                        help="Published R143 directory containing recfast_refinement.patch and hyrec_adapter.c")
    args = parser.parse_args()
    work, package = args.work_dir.resolve(), args.package_dir.resolve()
    for executable in ["git", "make", "gfortran", "gcc"]:
        if shutil.which(executable) is None:
            raise RuntimeError(f"Install {executable} before invoking this script; it does not install packages")
    patch, adapter = package / "recfast_refinement.patch", package / "hyrec_adapter.c"
    require_hash(patch, PATCH_SHA256)
    require_hash(adapter, HYREC_ADAPTER_SHA256)
    work.mkdir(parents=True, exist_ok=True)
    source = work / "CAMB_source"
    compiler = output("gfortran", "--version").splitlines()[0]
    prepare_camb(source, patch)
    run("make", "-C", source / "fortran", "python", "CLUSTER_SAFE=1", "COMPILER=gfortran", "-j1")
    baseline = save_camb_package(source, work / "compiled_base", fine=False,
                                 compiler=compiler, patch=patch)
    run("git", "apply", "--check", patch, cwd=source)
    run("git", "apply", patch, cwd=source)
    require_hash(source / "fortran/recfast.f90", RECFAST_FINE_SHA256)
    run("make", "-C", source / "fortran", "python", "CLUSTER_SAFE=1", "COMPILER=gfortran", "-j1")
    refined = save_camb_package(source, work / "compiled_fine", fine=True,
                                compiler=compiler, patch=patch)

    hyrec = work / "HYREC-2"
    checkout(HYREC_URL, HYREC_SHA, hyrec)
    if output("git", "diff", "HEAD", "--name-only", cwd=hyrec):
        raise RuntimeError("HYREC has tracked edits; refusing to compile them")
    library = work / "libhyrec_r143.so"
    gcc_args = ["gcc", "-O2", "-std=gnu99", "-shared", "-fPIC", "-DCAMB", '-DHYRECPATH="./"',
                "-I", str(hyrec), *[str(hyrec / f) for f in HYREC_SOURCES], str(adapter),
                "-lm", "-o", str(library)]
    run(*gcc_args)
    receipt = {
        "base": baseline,
        "fine": refined,
        "hyrec": {"source_sha": HYREC_SHA, "compiler": output("gcc", "--version").splitlines()[0],
                  "source_files": HYREC_SOURCES, "flags": '-O2 -std=gnu99 -shared -fPIC -DCAMB -DHYRECPATH="./"',
                  "adapter_sha256": sha256(adapter), "library_sha256": sha256(library)},
        "physics_runs_performed": 0,
        "paths": {"camb_base_prefix": str(work / "compiled_base"),
                  "camb_fine_prefix": str(work / "compiled_fine"),
                  "hyrec_source": str(hyrec), "hyrec_library": str(library)},
    }
    (work / "BUILD_RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
