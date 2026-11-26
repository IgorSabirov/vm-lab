"""Replay the bounded R143 Tarucha / transport-donor comparison.

Source facts are in DEVICES.json. No fit to an experimental energy curve is made.
The oscillator is an analytical control; the four-state Lindblad model is Emary's
donor, not the 216-state E002c production model. E002c operators are checked by
operator_control.calculate(), with no new trajectory integration.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np
import scipy

HERE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_lock():
    lock = json.loads((HERE / "LOCK.json").read_text())
    for name, expected in lock["frozen_sha256"].items():
        actual = sha256(HERE / name)
        if actual != expected:
            raise ValueError(f"Frozen input/code changed: {name}")
    return lock


def oscillator(delta, nmax, energy_scale_meV, cutoff):
    """B=0, two spin states per orbital, fixed geometric-mean confinement.

    Delta_2(N)-U = eps_(N+1)-eps_N for a constant-interaction Hamiltonian.
    U is deliberately not fitted: subtracting it removes an arbitrary constant.
    """
    el = energy_scale_meV / math.sqrt(delta)
    es = energy_scale_meV * math.sqrt(delta)
    orbitals = sorted(((nl + .5) * el + (ns + .5) * es, nl, ns)
                      for nl in range(cutoff + 1)
                      for ns in range(cutoff + 1))
    spin_levels = sorted([energy for energy, _, _ in orbitals for spin in range(2)])
    # First excluded orbital along either coordinate must lie above retained levels.
    first_excluded = min((cutoff + 1.5) * el + .5 * es,
                         .5 * el + (cutoff + 1.5) * es)
    assert first_excluded > spin_levels[nmax] + 1e-9
    energies = np.r_[0., np.cumsum(spin_levels[:nmax + 1])]
    rows = []
    for n in range(1, nmax + 1):
        spacing = spin_levels[n] - spin_levels[n - 1]
        second_difference = energies[n + 1] - 2 * energies[n] + energies[n - 1]
        assert abs(spacing - second_difference) < 1e-9
        rows.append({"delta": delta, "N": n, "Delta2_minus_U_meV": float(spacing)})
    return rows


def emary_stationary(phi, t=1., gamma=1.):
    """Eq(1,2), basis vacuum,1,2,3; global occupation <=1 and two sources."""
    h = np.zeros((4, 4), complex)
    h[1, 2] = t * np.exp(1j * phi)
    h[2, 1] = h[1, 2].conjugate()
    h[1, 3] = h[3, 1] = h[2, 3] = h[3, 2] = t
    jumps = []
    for target, source in [(1, 0), (2, 0), (0, 3)]:
        c = np.zeros((4, 4), complex)
        c[target, source] = math.sqrt(gamma)
        jumps.append(c)

    def rhs(rho):
        out = -1j * (h @ rho - rho @ h)
        for c in jumps:
            q = c.conj().T @ c
            out += c @ rho @ c.conj().T - .5 * (q @ rho + rho @ q)
        return out

    # Build the superoperator from its action, avoiding vectorisation-convention
    # assumptions in a hardcoded Kronecker formula.
    basis = np.eye(16).reshape(16, 4, 4)
    liouvillian = np.column_stack([rhs(e).ravel() for e in basis])
    trace_row = np.eye(4).ravel()
    system = np.vstack([liouvillian, trace_row])
    target = np.r_[np.zeros(16, complex), 1.]
    vector, _, rank, _ = np.linalg.lstsq(system, target, rcond=None)
    rho = vector.reshape(4, 4)
    assert rank == 16, "Unique trace-one stationary state is required."
    residual = float(np.max(np.abs(rhs(rho))))
    hermitian_error = float(np.max(np.abs(rho - rho.conj().T)))
    eigenvalues = np.linalg.eigvalsh((rho + rho.conj().T) / 2)
    assert residual < 1e-12 and hermitian_error < 1e-12
    assert abs(np.trace(rho) - 1) < 1e-12 and min(eigenvalues) > -1e-12
    current = float((gamma * rho[3, 3]).real)
    # Specialisation of Emary Eq(7): t12=t13=t23=t, Delta=epsilon=0.
    analytic = 4 * gamma * t*t * math.sin(phi)**2 / (gamma*gamma + 14*t*t*math.sin(phi)**2)
    assert abs(current - analytic) < 1e-12
    return {"phi_over_pi": phi / math.pi, "I_over_e": current,
            "analytic_I_over_e": analytic, "absolute_error": abs(current - analytic),
            "stationarity_residual": residual, "minimum_density_eigenvalue": float(min(eigenvalues))}


def calculate(lock):
    p = lock["oscillator"]
    rows = []
    shell_sets = {}
    for delta in p["delta_values"]:
        result = oscillator(delta, p["N_max"], p["energy_scale_meV"], p["basis_cutoff"])
        larger = oscillator(delta, p["N_max"], p["energy_scale_meV"], 2*p["basis_cutoff"])
        assert result == larger
        rows.extend(result)
        shell_sets[str(delta)] = [r["N"] for r in result if r["Delta2_minus_U_meV"] > 1e-9]
    assert shell_sets["1.0"] == [2, 6, 12, 20, 30, 42]
    assert shell_sets["2.0"] == [2, 4, 8, 12, 18, 24, 32, 40]
    for row in rows:
        assert row["Delta2_minus_U_meV"] >= -1e-12
        if row["N"] % 2:
            assert abs(row["Delta2_minus_U_meV"]) < 1e-12

    devices = json.loads((HERE / "DEVICES.json").read_text())
    geometry = []
    for device in devices["austing_1999"]:
        if device["id"] == "W":
            continue  # at circular degeneracy the noninteger rank rule does not apply
        delta_surrogate = device["mesa_L_um"] / device["mesa_S_um"]
        assert delta_surrogate != math.floor(delta_surrogate)
        # Rank of (0,1) among spatial orbitals: count levels below it explicitly.
        below = sum(nl + delta_surrogate*ns < delta_surrogate - 1e-12
                    for nl in range(8) for ns in range(8))
        rank = below + 1
        assert rank == math.floor(delta_surrogate) + 2
        geometry.append({"device": device["id"], "delta_surrogate_L_over_S": delta_surrogate,
                         "predicted_first_upmoving_pair": rank,
                         "published_first_upmoving_pair": device["first_upmoving_pair"],
                         "matches": rank == device["first_upmoving_pair"]})
    assert [r["matches"] for r in geometry] == [True, False, False]

    currents = [emary_stationary(math.pi*x) for x in lock["emary"]["phi_over_pi"]]
    assert abs(currents[2]["I_over_e"] - 4/15) < 1e-12
    for x in [.13, .37]:
        assert abs(emary_stationary(math.pi*x)["I_over_e"] -
                   emary_stationary(math.pi*(x+1))["I_over_e"]) < 1e-12

    from operator_control import calculate as operator_calculate
    operators = operator_calculate()
    summary = {
        "id": "R143-E01-TARUCHA-E002c-v1", "scientific_acceptance": False,
        "status": "SOURCE_MAP_AND_BOUNDED_CONTROLS_EXECUTED",
        "oscillator": {"conditions": p, "positive_orbital_gap_N": shell_sets,
                       "published_1996_enhanced_N": [2, 6, 12],
                       "ideal_extensions_not_measurements_in_1996": [20, 30, 42],
                       "at_N4_isotropic_gap_meV": next(r["Delta2_minus_U_meV"] for r in rows if r["delta"] == 1 and r["N"] == 4),
                       "scope": "Spin-degenerate constant-interaction control; exchange, Hund-rule peaks, N-dependent capacitance and confinement are excluded. No experimental fit."},
        "mesa_equals_confinement_negative_control": geometry,
        "emary_donor_stationary_current": currents,
        "E002c_operator_control": operators,
        "remaining_gap": "A calibrated multi-orbital spinful charging Hamiltonian and measured gate/energy map are needed to predict Tarucha addition spectra from a new model. Existing E002c has no such electron-number support or calibration.",
        "statistical_scope": "Published text values and model identities. No covariance, significance test or blind experimental validation is claimed.",
    }
    return summary, rows


def plot(rows, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(9.4, 6.1), sharex=True, sharey=True)
    for ax, delta in zip(axes.ravel(), [1., 1.5, 2., 3.2]):
        r = [r for r in rows if r["delta"] == delta and r["N"] <= 20]
        ax.vlines([a["N"] for a in r], 0, [a["Delta2_minus_U_meV"] for a in r], color="#136f87", lw=1.8)
        ax.scatter([a["N"] for a in r], [a["Delta2_minus_U_meV"] for a in r], color="#136f87", s=18, zorder=3)
        ax.set_title(rf"$\delta={delta:g}$")
        ax.set_xticks([2, 6, 12, 16, 20]); ax.grid(axis="y", alpha=.22)
        ax.set_ylim(-.13, 3.35)
    fig.supxlabel("Electron number N")
    fig.supylabel(r"Orbital contribution $\Delta_2(N)-U$ (meV)")
    fig.suptitle("Ideal addition spectra at fixed geometric-mean confinement: 3 meV\nModel control; experimental data are not plotted", fontsize=12)
    fig.tight_layout(rect=(.025, .02, 1, .91))
    fig.savefig(output, dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Recompute and compare saved scientific values without changing files.")
    args = parser.parse_args()
    started = time.perf_counter()
    lock = check_lock()
    summary, rows = calculate(lock)
    numerical_seconds = time.perf_counter() - started
    destination = HERE / "results"
    if args.check:
        expected = json.loads((destination / "SUMMARY.json").read_text())
        def compare(a, b, path="root"):
            if isinstance(a, dict):
                assert a.keys() == b.keys(), path
                for key in a: compare(a[key], b[key], path+"."+key)
            elif isinstance(a, list):
                assert len(a) == len(b), path
                for i, (aa, bb) in enumerate(zip(a,b)): compare(aa,bb,path+f"[{i}]")
            elif isinstance(a, float):
                assert math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-12), (path,a,b)
            else:
                assert a == b, (path,a,b)
        compare(summary, expected)
        with (destination / "addition_spectra.csv").open() as stream:
            saved = list(csv.DictReader(stream))
        assert len(saved) == len(rows)
        for a, b in zip(rows, saved):
            for key in a:
                assert abs(float(a[key]) - float(b[key])) < 1e-12
        print("PASS: frozen inputs, spectral cutoff, addition differences, donor stationary current, E002c operators, saved results.")
        return
    destination.mkdir(exist_ok=True)
    (destination / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    with (destination / "addition_spectra.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    plot(rows, destination / "addition_spectra.png")
    receipt = {
        "protocol_sha256": sha256(HERE / "LOCK.json"),
        "frozen_sha256": lock["frozen_sha256"],
        "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
        "numerical_seconds": numerical_seconds, "total_seconds_including_plot_and_write": time.perf_counter()-started,
        "previous_operator_probe_seconds": .05443655700037198,
        "new_E002c_trajectories": 0,
        "execution_kind": "Finite-spectrum enumeration and small stationary/operator linear algebra; not an E002c production run.",
    }
    (destination / "RUN_RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"status": summary["status"], "numerical_seconds": numerical_seconds,
                      "rows": len(rows), "source_surrogate_matches": [r["matches"] for r in summary["mesa_equals_confinement_negative_control"]]}, indent=2))


if __name__ == "__main__":
    main()
