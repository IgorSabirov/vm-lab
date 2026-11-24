"""Audit public evidence for a matched E55 pair at two wave numbers."""
import argparse
import csv
import hashlib
import io
from itertools import combinations
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def fit_trace(t_ms, displacement, frequency_hz, free_offset=False):
    phase = 2 * np.pi * frequency_hz * np.asarray(t_ms) / 1000
    columns = [np.sin(phase), np.cos(phase)]
    if free_offset:
        columns.append(np.ones_like(phase))
    design = np.column_stack(columns)
    coeff, _, _, _ = np.linalg.lstsq(design, displacement, rcond=None)
    residual = displacement - design @ coeff
    variance = residual @ residual / (len(displacement) - len(coeff))
    errors = np.sqrt(variance * np.diag(np.linalg.inv(design.T @ design)))
    return {"points": len(displacement), "sin_um": round(float(coeff[0]), 6),
            "cos_um": round(float(coeff[1]), 6), "se_cos_um": round(float(errors[1]), 6)}


def digitize_theses(pc_path, mg_path):
    """Read the printed FIT curves, with axis ticks in image pixels or PDF points."""
    import fitz
    from PIL import Image
    from scipy.optimize import least_squares

    def verified_pdf(path, previous_figure):
        fingerprint = json.loads((ROOT / "eos" / previous_figure).read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest() != fingerprint["pdf_sha256"]:
            raise ValueError(f"Unexpected PDF edition: {path.name}")
        return fitz.open(path)

    def fitted_period(t_ms, ordinate, nominal):
        t = t_ms / 1000
        def design(frequency):
            angle = 2 * np.pi * frequency * t
            return np.column_stack((np.sin(angle), np.cos(angle), np.ones_like(t)))
        initial = np.linalg.lstsq(design(nominal), ordinate, rcond=None)[0]
        def residual(params):
            return design(params[0]) @ params[1:] - ordinate
        result = least_squares(residual, [nominal, *initial], loss="soft_l1", f_scale=1)
        return round(float(result.x[0]), 3)

    pc_curves = []
    with verified_pdf(pc_path, "figure_5_10.json") as doc:
        image_ids = {image[0] for image in doc[124].get_images()}
        # Pixel columns of the 140 and 260 ms spines of Fig. 5.4(b).
        panels = [(1126, 3, 744, 15), (1127, 5, 746, 42), (1125, 1, 649, 70)]
        for xref, left, right, nominal in panels:
            if xref not in image_ids:
                raise ValueError("Missing Fig. 5.4 panel")
            raw = doc.extract_image(xref)["image"]
            rgb = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))
            blue = np.all(rgb == [23, 60, 126], axis=2)
            x = [i for i in range(left + 3, right - 2) if np.any(blue[:, i])]
            y = np.array([np.median(np.flatnonzero(blue[:, i])) for i in x])
            t = 140 + (np.array(x) - left) * 120 / (right - left)
            pc_curves.append({"label_hz": nominal, "fitted_line_hz": fitted_period(t, y, nominal)})

    with verified_pdf(mg_path, "figure_4_9.json") as doc:
        paths = doc[63].get_drawings()
        blue, = [p for p in paths if len(p["items"]) > 200 and p["color"][2] > 0.45]
        x, y = np.array([(item[1].x, item[1].y) for item in blue["items"] if item[0] == "l"]).T
        visible = (x >= 240.710) & (x <= 390.710)
        # Tick coordinates at 150/250 ms and +2/0/-2 micrometres, respectively.
        t = 150 + (x[visible] - 250.256) * 100 / (381.163 - 250.256)
        displacement = (97.7531 - y[visible]) * 4 / (107.3971 - 88.1081)
        coeff = fit_trace(t, displacement, 42.5)
        # Curve vertices describe a printed fit. Their scatter is not a measurement error.
        mg_curve = {"label_hz": 42.5, "fitted_line_hz": fitted_period(t, displacement, 42.5),
                    "abs_cos_um_from_published_fit": abs(coeff["cos_um"])}
    return {"Christodoulou_fig_5_4b": pc_curves, "Galka_fig_4_3": mg_curve}


def closest_bins(table, f1, f2):
    """Score every ordered pair. Absolute scale agreement is not a run identifier."""
    rows = np.loadtxt(io.BytesIO(table), skiprows=1)
    candidates = []
    for i, first in enumerate(rows):
        for j, second in enumerate(rows):
            if first[0] >= second[0]:
                continue
            scale_a, scale_b = f1 / first[0], f2 / second[0]
            mismatch = abs(scale_b / scale_a - 1)
            candidates.append((mismatch, i, j, scale_a, scale_b))
    mismatch, i, j, scale_a, scale_b = min(candidates)
    return {"data_rows": [i + 1, j + 1], "normalized_frequencies": rows[[i, j], 0].tolist(),
            "inferred_scales_hz": [round(scale_a, 6), round(scale_b, 6)],
            "relative_difference_ppm": round(1e6 * mismatch, 3),
            "absorptive_response": rows[[i, j], 1].tolist(),
            "tabulated_errors": rows[[i, j], 2].tolist()}


def pair_counts(rows):
    pairs = list(combinations(rows, 2))
    both = [(a, b) for a, b in pairs if a["L_drive_nom_um"] and b["L_drive_nom_um"]]
    return {"rows": len(rows), "unordered_pairs": len(pairs), "missing_one_or_both_lengths": len(pairs) - len(both),
            "known_same_length": sum(a["L_drive_nom_um"] == b["L_drive_nom_um"] for a, b in both),
            "known_different_length": sum(a["L_drive_nom_um"] != b["L_drive_nom_um"] for a, b in both)}


def audit():
    figures = json.loads((HERE / "repeat_boxes_figures.json").read_text())
    manifest = json.loads((ROOT / "data/manifest.json").read_text())
    archive = ROOT / "data/cambridge.zip"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("Unexpected Cambridge archive")
    with ZipFile(archive) as z:
        trace = z.read("Figure 1/Fig1c_oscillation.txt")
        t, y = np.loadtxt(io.BytesIO(trace), skiprows=1).T
        fits = {name: fit_trace(t, y, 25, free_offset=offset)
                for name, offset in [("published_function", False), ("with_intercept", True)]}
        scales = {}
        for name, panel in [("cold", "Top"), ("warm", "Bottom")]:
            table = z.read(f"Figure 2/Fig2a_response_{panel}Panel.txt")
            scales[name] = {str(f): closest_bins(table, 25, f) for f in [42, 42.5]}
    cold = scales["cold"]["42.5"]
    scale = np.pi * (2 * np.pi * cold["inferred_scales_hz"][0])**2 * 1e-6 / (8 * 0.074)
    amplitudes = [abs(fits["published_function"]["cos_um"]),
                  figures["Galka_fig_4_3"]["abs_cos_um_from_published_fit"]]
    with (ROOT / "eos/geometry.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    return {"parent": "R143/E55", "counts_all_conditions": pair_counts(rows),
            "counts_with_D2": pair_counts([r for r in rows if r["D2_graph_hbar_over_m"]]),
            "Cambridge_fig1c_fit_um": fits, "paired_frequency_grid_candidates": scales,
            "cold_candidate_conditional_abs_normalized_amplitudes": [round(float(scale*a), 6) for a in amplitudes],
            "assumptions": {"force_over_mass_m_s2": 0.074, "force_source": "Fig. 2, unverified for individual time traces",
                            "frequencies": "fixed at figure labels; closest ordered pair per spectrum by relative difference",
                            "short_box_series_temperature": None, "Galka_fig_4_3_box": None},
            "matched_pair_status": "not_identified_in_public_inputs", "observed_width_ratio": None,
            "constant_D2_nominal_prediction": (33/23)**2}


def write_json(name, data):
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theses", nargs=2, type=Path, metavar=("CHRISTODOULOU_PDF", "GALKA_PDF"))
    args = parser.parse_args()
    if args.theses:
        write_json("repeat_boxes_figures.json", digitize_theses(*args.theses))
    write_json("repeat_boxes.json", audit())
