"""R135 GW sidecar: propagate a per-log-frequency emission spectrum; project observed bands."""

import argparse
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import sys
from zipfile import ZipFile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "donors"))
from fetch import acquire
from extract import article, one

H100 = 100_000 / 3.0856775814913673e22  # (100 km/s/Mpc) in s^-1


def positive(x):
    if not np.isfinite(x) or x <= 0:
        raise ValueError("Expected a positive finite physical quantity")
    return float(x)


def spectrum(history):
    """d rho_GW / (rho_tot,* d ln f*) at end of emission. Frequencies in cycles/s."""
    h = positive(history["H_star_s_inv"])
    source = history["source"]
    if source["kind"] == "tabulated":
        f = np.asarray(source["f_star_Hz"], dtype=float)
        w = np.asarray(source["omega_star"], dtype=float)
    elif source["kind"] == "sound":
        r = positive(source["R_star_light_seconds"])
        cs = positive(source["sound_speed_c"])
        kinetic = positive(source["bulk_kinetic_over_total_density"])
        if cs > 1 or kinetic > 1 or h * r >= 1:
            raise ValueError("Acoustic fit outside subhorizon or fluid domain")
        kpeak_r = positive(source["k_peak_R"])
        duration = min(1.0, h * positive(source["duration_seconds"]))
        peak = (
            0.687 * positive(source["tilde_Omega"]) * kinetic**2 * duration * h * r / cs
        )
        low, high = map(positive, source["frequency_support_Hz"])
        f = np.geomspace(low, high, 2049)
        x = 2 * math.pi * f * r / kpeak_r
        w = peak * x**3 * (7 / (4 + 3 * x * x)) ** 3.5
    else:
        raise ValueError("Unknown source mechanism")
    if (
        f.ndim != 1
        or len(f) < 2
        or f.shape != w.shape
        or not np.isfinite(f).all()
        or not np.isfinite(w).all()
        or not np.all(np.diff(f) > 0)
        or np.any(w < 0)
        or f[0] < h / (2 * math.pi)
    ):
        raise ValueError(
            "Expected ordered subhorizon emission spectrum with finite nonnegative density"
        )
    if np.trapezoid(w, np.log(f)) > 1:
        raise ValueError("GW energy exceeds the total energy at emission")
    return f, w


def transfer(history):
    for key in ("point_id", "history_id", "source_provenance"):
        if not isinstance(history.get(key), str) or not history[key].strip():
            raise ValueError("Missing " + key)
    a = positive(history["a_star_over_a0"])
    h = positive(history["H_star_s_inv"])
    hubble0 = positive(history["H0_s_inv"])
    if a > 1:
        raise ValueError("Emission after today")
    f, w = spectrum(history)
    f0 = f * a
    omega0 = w * (h / hubble0) ** 2 * a**4
    budget = []
    for epoch in history["bbn_epochs"]:
        ae = positive(epoch["a_over_a0"])
        he = positive(epoch["H_s_inv"])
        if ae > 1:
            raise ValueError("BBN epoch after today")
        cutoff = ae * he / (2 * math.pi * a)
        fraction = 0.0
        if ae >= a and cutoff < f[-1]:
            start = max(f[0], cutoff)
            grid = np.r_[start, f[f > start]]
            integral = np.trapezoid(np.interp(np.log(grid), np.log(f), w), np.log(grid))
            fraction = float(integral * (h / he) ** 2 * (a / ae) ** 4)
            if fraction > 1:
                raise ValueError("Inconsistent background energy at BBN")
        budget.append({"a_over_a0": ae, "rho_GW_over_rho_total": fraction})
    return f0, omega0, budget


def detector_projection(f, omega, h0, paths):
    f = np.asarray(f, float)
    omega = np.asarray(omega, float)
    if (f.ndim != 1 or len(f) < 2 or omega.shape != f.shape
            or not np.isfinite(f).all() or np.any(f <= 0) or np.any(np.diff(f) <= 0)
            or not np.isfinite(omega).all() or np.any(omega < 0)):
        raise ValueError("Invalid nodal present-day GW spectrum")
    return _detector_projection(
        lambda freq: np.interp(np.log(freq), np.log(f), omega, left=0, right=0),
        float(f[0]), float(f[-1]), h0, paths)


def detector_projection_cells(edges, omega, h0, paths):
    """Project cell-constant d rho/d ln f without changing its finite support."""
    edges = np.asarray(edges, float)
    omega = np.asarray(omega, float)
    if (edges.ndim != 1 or len(edges) < 2 or omega.shape != (len(edges)-1,)
            or not np.isfinite(edges).all() or np.any(edges <= 0)
            or np.any(np.diff(edges) <= 0) or not np.isfinite(omega).all()
            or np.any(omega < 0)):
        raise ValueError("Invalid cell-constant present-day GW spectrum")
    def predict(freq):
        freq = np.asarray(freq, float)
        indexes = np.searchsorted(edges, freq, side="right")-1
        result = np.zeros_like(freq)
        inside = (indexes >= 0) & (indexes < len(omega))
        result[inside] = omega[indexes[inside]]
        return result
    return _detector_projection(predict,float(edges[0]),float(edges[-1]),h0,paths)


def _detector_projection(predict, low_frequency, high_frequency, h0, paths):
    h0 = positive(h0)
    # G2502630 used H0=67.9 km/s/Mpc. C and its sigma are per-frequency-bin estimates.
    grid, c, err, mask = np.loadtxt(paths["lvk-o4a-hl"], unpack=True)
    use = (mask == 1) & np.isfinite(c) & np.isfinite(err) & (err > 0) & np.isfinite(grid) & (grid > 0)

    o = predict(grid[use]) * (h0 / (0.679 * H100)) ** 2
    dll = np.sum((c[use] * o - 0.5 * o * o) / err[use] ** 2)
    with ZipFile(paths["ng15-kde"]) as z:
        member = "ceffyl_data/30f_fs{hd}_ceffyl/freqs.npy"
        pta = np.load(BytesIO(z.read(member)), allow_pickle=False)
    # One-sided residual PSD S_r=H0^2 Omega/(8 pi^4 f^5); rho_i^2=S_r/Tspan.
    df = pta[0]
    if not np.allclose(pta, np.arange(1, len(pta) + 1) * df, rtol=1e-5, atol=0):
        raise ValueError("Unknown PTA Fourier frequency spacing")
    residual = np.sqrt(h0**2 * predict(pta) * df / (8 * math.pi**4 * pta**5))
    paper = article(paths["lvk-o4c1-paper"], "macros/nominal_PE.tex")
    references = {}
    for name, macro in [("flat", "Zero"), ("CBC_2_over_3", "TwoThirds")]:
        value, power = one(
            r"\\newcommand\{\\ULLogUnifAll"
            + macro
            + r"\}\{\\ensuremath\{([\d.]+)\\times 10\^\{(-?\d+)\}",
            paper,
        )
        references[name] = float(value) * 10 ** int(power)
    return dict(
        LVK_O1_O4c1_published_loguniform_UL95_at_25Hz=references,
        LVK_O4a_HL=dict(
            unmasked_bins=int(sum(use)),
            overlap_bins=int(sum((grid[use] >= low_frequency) & (grid[use] <= high_frequency))),
            conditional_delta_logL_vs_zero=float(dll),
            inference_scope="diagonal Gaussian delta log L at fixed foreground and calibration",
        ),
        NG15_HD=dict(
            f_Hz=pta.tolist(),
            rms_residual_s=residual.tolist(),
            overlap_bins=int(sum((pta >= low_frequency) & (pta <= high_frequency))),
            inference_scope="predicted Fourier-bin RMS only; not an HD likelihood",
        ),
    )


def run(history, files):
    f, o, b = transfer(history)
    return {
        "point_id": history["point_id"],
        "history_id": history["history_id"],
        "source_provenance": history["source_provenance"],
        "source_kind": history["source"]["kind"],
        "f_today_Hz": f.tolist(),
        "Omega_GW_today": o.tolist(),
        "bbn_budget": b,
        "detectors": detector_projection(f, o, history["H0_s_inv"], files),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("history", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--offline", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    inputs = json.loads(args.history.read_text())
    data = acquire(args.cache, {"gw"}, args.offline)
    result = run(inputs, data)
    result["input_sha256"] = hashlib.sha256(args.history.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
