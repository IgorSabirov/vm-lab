"""R143: small charge-support and donor-transfer checks on pinned E002c code.

No Liouvillian construction, trajectory integration, fitting, or production run.
``calculate()`` has no working-directory dependency and returns deterministic data.
The two local source copies are checked before their bytes are executed.
"""
import hashlib
import json
import sys
import types
from pathlib import Path


SOURCE_COMMIT = "acb401f9972e064779a7c7345938cb1aea2997f6"
IDENTICAL_CALIBRATION_COMMIT = "ca15a197834bc3193f3da87d1bbd9ab1a538bf90"
SOURCE_FILES = {
    "e002_exp/model.py": {
        "sha256": "9b19bb41e031b50ada0c1acd81df8a1ce3deddfc78e5a6dbfb56e048772f28f2",
        "git_blob": "272309e9921912ce08b1e2a6498edf6980f3fa55",
    },
    "e002c_exp/model.py": {
        "sha256": "fc8fa406319f2a58aa872109c340dc40d01447cafb210773cb63893d0e3b9491",
        "git_blob": "972fe5318977181650f8c63009839ebb57aa916d",
    },
}


def _verified_modules():
    """Load verified bytes without using a possibly cached project module."""
    input_root = Path(__file__).resolve().parent / "inputs"
    verified = {}
    for relative, metadata in SOURCE_FILES.items():
        path = input_root / relative
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != metadata["sha256"]:
            raise ValueError(f"Pinned input hash mismatch: {relative}: {digest}")
        verified[relative] = (path, raw)

    # e002c imports e002_exp.model by its historical name. Temporarily provide
    # exactly that pinned dependency, then restore the caller's module registry.
    names = ("e002_exp", "e002_exp.model", "e002c_exp", "e002c_exp.model")
    previous = {name: sys.modules.get(name) for name in names}
    loaded = {}
    try:
        for package_name in ("e002_exp", "e002c_exp"):
            package = types.ModuleType(package_name)
            package.__path__ = [str(input_root / package_name)]
            sys.modules[package_name] = package
            relative = f"{package_name}/model.py"
            path, raw = verified[relative]
            name = f"{package_name}.model"
            module = types.ModuleType(name)
            module.__file__ = str(path)
            module.__package__ = package_name
            sys.modules[name] = module
            package.model = module
            exec(compile(raw, str(path), "exec"), module.__dict__)
            loaded[package_name] = module
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return loaded["e002_exp"], loaded["e002c_exp"]


def calculate():
    """Return the small control; runtimes and environment belong in the receipt."""
    base, e002c = _verified_modules()
    import numpy as np

    o = e002c.operators()
    charge = sum(o["n"])
    eigenvalues, ranks = np.unique(charge.diagonal().real, return_counts=True)
    h, jumps, _, _, dims = base.build_model(e002c.BASE)
    jd = dict(jumps)
    charge_rhs = 1j * (h @ charge - charge @ h)
    charge_rhs += sum(base.adjoint_jump(c, charge) for _, c in jumps)
    expected = (e002c.BASE["kappa_in"] * (o["eye"] - o["n"][0])
                - e002c.BASE["kappa_out"] * o["n"][2])
    algebra = {
        "H_charge_commutator_max_abs": base.maxabs(h @ charge - charge @ h),
        "source_charge_shift_plus_one_residual": base.maxabs(
            charge @ jd["source_0"] - jd["source_0"] @ charge - jd["source_0"]),
        "sink_charge_shift_minus_one_residual": base.maxabs(
            charge @ jd["sink_2"] - jd["sink_2"] @ charge + jd["sink_2"]),
        "open_charge_balance_residual": base.maxabs(charge_rhs - expected),
        "local_double_raising_residual": base.maxabs(o["up"][0] @ o["up"][0]),
        "cross_site_raising_commutator": base.maxabs(
            o["up"][0] @ o["up"][1] - o["up"][1] @ o["up"][0]),
        "cross_site_raising_anticommutator": base.maxabs(
            o["up"][0] @ o["up"][1] + o["up"][1] @ o["up"][0]),
    }
    dark = np.zeros(216, complex)
    # Nodes 100 and 010; the frozen LLL edge state is ternary 222 = 26.
    dark[4 * 27 + 26] = 1 / np.sqrt(2)
    dark[2 * 27 + 26] = -1 / np.sqrt(2)
    source_on_dark = float(np.linalg.norm(jd["source_0"] @ dark) ** 2)
    sink_on_dark = float(np.linalg.norm(jd["sink_2"] @ dark) ** 2)
    dimensions = []
    for phi_over_pi in (0., .5, 1.):
        for mask in range(8):
            hm = e002c.sector_hamiltonian(mask, phi=phi_over_pi * np.pi)
            _, d, iso, inter, info = e002c.dark_projectors(hm)
            dimensions.append({
                "phi_over_pi": phi_over_pi,
                "mask": mask,
                "dark_dimension": info["D"]["dimension"],
                "isolated_dimension": int(round(np.trace(iso).real)),
                "interference_dimension": int(round(np.trace(inter).real)),
                "H_invariance_residual": float(np.linalg.norm((np.eye(3)-d) @ hm @ d)),
                "observability_residual": info["D"]["residual"],
            })

    assert dims == [2, 2, 2, 3, 3, 3]
    assert eigenvalues.tolist() == [0., 1., 2., 3.]
    assert ranks.tolist() == [27, 81, 81, 27]
    for name, value in algebra.items():
        if name != "cross_site_raising_anticommutator":
            assert value < 1e-12, (name, value)
    assert algebra["cross_site_raising_anticommutator"] == 2.
    assert abs(source_on_dark - .25) < 1e-12
    assert sink_on_dark < 1e-12
    assert len(dimensions) == 24
    assert [row["dark_dimension"] for row in dimensions if row["mask"] == 7] == [1, 0, 1]
    for row in dimensions:
        assert row["H_invariance_residual"] < 1e-12, row
        assert row["observability_residual"] < 1e-12, row
        assert row["dark_dimension"] == row["isolated_dimension"] + row["interference_dimension"], row

    return {
        "source_commit": SOURCE_COMMIT,
        "identical_calibration_commit": IDENTICAL_CALIBRATION_COMMIT,
        "source_files": SOURCE_FILES,
        "dimension": int(h.shape[0]),
        "subsystem_dimensions": dims,
        "node_charge_sectors": [dict(N=int(n), rank=int(r)) for n, r in zip(eigenvalues, ranks)],
        "tarucha_closure_support": {str(n): bool(n in eigenvalues) for n in [2, 6, 12, 20, 30, 42]},
        "support_caveat": (
            "N=2 is an excitation-number sector, not a calibrated two-electron shell or spinful orbital model. "
            "The defined charge operator has no N=6 or N=12 sector."),
        "algebra": algebra,
        "frozen_LLL_D": {
            "source_rate_on_D": source_on_dark,
            "sink_rate_on_D": sink_on_dark,
            "interpretation": (
                "An H-hop dark vector is not an absorbing state under the full E002c pump. "
                "No stationary-state or spectral-gap claim."),
        },
        "one_excitation_mask_checks": dimensions,
        "scientific_acceptance": False,
    }


if __name__ == "__main__":
    print(json.dumps(calculate(), indent=2, ensure_ascii=False, allow_nan=False))
