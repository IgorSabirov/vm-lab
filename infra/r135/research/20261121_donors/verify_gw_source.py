"""Reproduce the #174 input and kernel checks. All tensor stresses are manufactured."""
import argparse
import hashlib
import importlib.util
import json
import math
import sys
import tempfile
from types import ModuleType
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from scipy.integrate import quad, solve_ivp
from scipy.interpolate import PchipInterpolator

from bubble_contacts import first_contacts

SOFTWARE = ("https://raw.githubusercontent.com/IgorSabirov/vm-lab/"
            "c3bc771d1daa292d5d9fd3e1d17bf4d3d6d01c92/"
            "analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/software/")
INPUTS = {
    "validation.json": (SOFTWARE + "donors/validation.json",
                        "b913bd500cb0025811a32f83dd4efd05ca7cfd6a723564e22d0eb50c7fb6401a"),
    "eos.py": ("https://raw.githubusercontent.com/pedrota2000/SNOBEX/"
               "098553176dcd4d2dc975c70fa2a22b7321ef27b1/snobex/eos.py",
               "380b8f527e182f6ef45657f929a6b6332bf6d924efa9855b99f0df6ced3b1e5c"),
    "r135geom/pockets.py": (SOFTWARE + "r135/pockets.py",
                            "7ced5b6a7df4bb8e0d54dc33fd5d54780b123ee64834a41504cf3f0346d85fa4"),
    "r135geom/common.py": (SOFTWARE + "r135/common.py",
                           "6d275d0fc494135051e0872c5d793edb438f6e43599f99c7b1ad72c5ba425fe5"),
    "p7.json": (SOFTWARE + "gw/integrated_reference/source_on_refined_P7_history.json",
                "701e44ee50414848ec0de83dc9d35d9b3f1bcbdb24678a70d71bdd7e0824526e"),
}


def read_inputs(directory, offline):
    directory.mkdir(parents=True, exist_ok=True)
    for name, (url, digest) in INPUTS.items():
        path = directory / name
        if path.exists():
            data = path.read_bytes()
        elif offline:
            raise FileNotFoundError(path)
        else:
            with urlopen(url, timeout=60) as response:
                data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Input checksum mismatch for {name}")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def check_eos(directory):
    spec = importlib.util.spec_from_file_location("snobex_eos_fixed", directory / "eos.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = json.loads((directory / "validation.json").read_text())["equilibrium_eos"]
    table = []
    for row in rows:
        t = row["T_over_Tc"]
        table.append([t, row["p_over_T4"] * t**4, row["rho_over_T4"] * t**4,
                      row["s_over_T3"] * t**3])
    table = np.asarray(table)
    t, p, e, s = table.T
    np.testing.assert_allclose(e + p, t * s, rtol=1e-12)
    # A secant across the two phases has no single-phase sound-speed meaning.
    slopes = np.diff(p) / np.diff(e)
    same_phase = (t[:-1] < 1) == (t[1:] < 1)
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "stable.txt"
        np.savetxt(path, table)
        try:
            module.load_custom_eos(path, Tc=1, cs2_from="pe")
        except ValueError as exc:
            message = str(exc)
            if "two c_s² = 0 turning points" not in message:
                raise
        else:
            raise AssertionError("The pinned equilibrium-only input unexpectedly passed")
    return {"rows": len(t), "T_over_Tc": [t.min(), t.max()],
            "same_phase_secants": int(same_phase.sum()),
            "same_phase_dp_de_range": [slopes[same_phase].min(), slopes[same_phase].max()],
            "loader_result": message}


def analytic_controls():
    factors = {}
    for w in (0.0, 1/3, 0.5, 0.99, 1.0):
        exponent = 1.5 * (w - 1)
        value = math.expm1(exponent * math.log(2)) / exponent if exponent else math.log(2)
        integral = quad(lambda y: y**(exponent-1), 1, 2)[0]
        np.testing.assert_allclose(value, integral, rtol=1e-12)
        factors[str(w)] = value

    # Static Poisson process, common speed, f0=0. Gamma=v=1 in test units.
    # I(t) = pi*t^4/3. Count successful centres through the instant I=1.
    end = (3/math.pi)**0.25
    intensity = quad(lambda b: 4*math.pi*(end-b)**3/3, 0, end)[0]
    ratio = quad(lambda b: math.exp(-math.pi*b**4/3), 0, end)[0] / end
    np.testing.assert_allclose(intensity, 1, rtol=1e-12)

    # h''+h=S with S constant on each half-period. Contract the two
    # retarded (h,h') response columns with cov(S1,S2), diagonal=(1,1).
    final = 2*math.pi
    columns = np.array([[quad(lambda t: fun(final-t), a, b)[0]
                         for a, b in ((0, math.pi), (math.pi, final))]
                        for fun in (math.sin, math.cos)])
    energies = {}
    for corr in (-1, 0, 1):
        cov = np.array([[1., corr], [corr, 1.]])
        energy = float(np.trace(columns @ cov @ columns.T)/2)
        np.testing.assert_allclose(energy, 4*(1-corr), atol=1e-12)
        energies[str(corr)] = round(energy, 12)
    positive_work = quad(lambda t: max(0., math.sin(t)), 0, final)[0]
    return {"xiao_y2": factors, "poisson_I": intensity,
            "actual_over_phantom_births_at_I1": ratio, "flat_mode_energy": energies,
            "positive_only_work_correlated": positive_work,
            "HR_v_over_beta": [v/5e5 for v in (.3,.5,.9)],
            "HR_mean_spacing_exponential": [(8*math.pi)**(1/3)*v/5e5 for v in (.3,.5,.9)]}


def contact_control():
    # The second event lies inside the first across the periodic seam.
    # Growth stalls precisely at the first contact, then resumes.
    events = {"birth_time_s": [0, .5, 1, 3.2],
              "centers_comoving_cm": [[.25, 0, 0], [9.875, 0, 0], [3.25, 0, 0], [6.25, 0, 0]]}
    rows = first_contacts(events, [0, 1, 2, 3, 4], [0, 1, 2, 2, 2.8], 10.)
    assert [r["event_index"] for r in rows] == [0, 2, 3]
    assert [r["first_contact_time_s"] for r in rows] == [2., 2., None]
    assert [r["comoving_radius_at_contact_cm"] for r in rows] == [2., 1., None]
    return rows


def native_population_control(directory):
    # Load just the two checksum-verified modules from #159, keeping its imports.
    name = "r135_geometry_fixed"
    package = ModuleType(name)
    package.__path__ = []
    sys.modules[name] = package
    for part in ("common", "pockets"):
        spec = importlib.util.spec_from_file_location(name+"."+part, directory/"r135geom"/(part+".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    pockets = sys.modules[name+".pockets"]
    t = np.linspace(0., 1., 101)
    rate = 3/math.pi
    box_size = 8.
    history = {"time_s": t, "scale_factor": np.ones_like(t),
               "nucleation_rate_cm3_s": np.full_like(t, rate),
               "wall_speed": np.full_like(t, 1/pockets.C_CM_S)}
    geom = pockets.avrami_geometry(history)
    np.testing.assert_allclose(geom["I"][-1], 1., atol=0.00011)
    expected_real = rate * box_size**3 * quad(lambda b: math.exp(-b**4), 0, 1)[0]
    counts = []
    for seed in range(16):
        events = pockets.sample_nucleations(history, box_size, seed)
        real = first_contacts(events, t, geom["comoving_wall_distance_cm"], box_size)
        counts.append([len(events["birth_time_s"]), len(real)])
    measured = np.asarray(counts)[:, 1]
    mean = measured.mean()
    sem = measured.std(ddof=1)/math.sqrt(len(measured))
    assert abs(mean - expected_real) < 4 * sem
    return {"seeds": list(range(16)), "box_cm": box_size, "duration_s": 1.,
            "intensity_at_end": geom["I"][-1], "events_and_accepted_per_seed": counts,
            "mean_accepted": mean, "analytic_expected_accepted": expected_real,
            "standard_error_over_seeds": sem}


def check_background(directory):
    # In physical seconds Lh = h_tt + 3H h_t + (k/a)^2 h. Source is a
    # manufactured value of 16*pi*G*Pi, in s^-2; no physical normalization.
    hst = json.loads((directory / "p7.json").read_text())
    times = np.asarray(hst["time_s"])
    scale = PchipInterpolator(times, hst["scale_factor"], extrapolate=False)
    hubble = PchipInterpolator(times, hst["H_s_inv"], extrapolate=False)
    start = times[0]
    end = start + 0.75
    assert end <= times[-1]
    k = 30 * scale(start) * hubble(start)
    mid = (start + end)/2
    cov = np.array([[1., 0.5], [0.5, 1.]])
    lower = np.linalg.cholesky(cov)

    def sources(t):
        j = int(t >= mid)
        f = (t - (mid if j else start))/(mid-start)
        values = np.zeros(2)
        if 0 < f < 1:
            values[j] = math.sin(math.pi*f)**2
        return values

    def matrix(t):
        return np.array([[0., 1.], [-(k/scale(t))**2, -3*hubble(t)]])

    def forward(t, state):
        dy = matrix(t) @ state.reshape(2, 2)
        dy[1] += sources(t) @ lower
        return dy.ravel()

    options = dict(method="DOP853", atol=1e-12, rtol=2e-10, max_step=(end-start)/60)
    direct = solve_ivp(forward, (start, end), np.zeros(4), dense_output=True, **options)
    assert direct.success
    output = []
    for target in (mid, start + .55, end):
        # Backward adjoint for the h_t row of the retarded propagator.
        adjoint = solve_ivp(lambda t, z: -matrix(t).T @ z, (target, start), [0., 1.],
                            dense_output=True, **options)
        assert adjoint.success
        nodes = [mid] if start < mid < target else []
        response = np.array([quad(lambda t: adjoint.sol(t)[1]*sources(t)[j],
                                  start, target, points=nodes, epsabs=1e-12)[0]
                             for j in range(2)])
        via_uetc = float(response @ cov @ response)
        velocity = direct.sol(target).reshape(2, 2)[1]
        via_ode = float(velocity @ velocity)
        relative = abs(via_ode-via_uetc)/via_ode
        if relative > 2e-6:
            raise AssertionError((target, via_ode, via_uetc))
        output.append(dict(time_s=float(target), ode_hdot_variance=via_ode,
                           uetc_hdot_variance=via_uetc, relative_difference=relative))
    return {"point": hst["point_id"], "k_over_aH_initial": 30, "probes": output}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    read_inputs(args.cache, args.offline)
    report = {"scope": "input applicability and manufactured tensor controls",
              "physical_X_source": False, "inputs": INPUTS, "eos": check_eos(args.cache),
              "controls": analytic_controls(), "filtered_births": contact_control(),
              "native_poisson": native_population_control(args.cache),
              "p7_tensor_check": check_background(args.cache)}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
