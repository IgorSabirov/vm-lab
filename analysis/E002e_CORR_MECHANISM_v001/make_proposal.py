"""Generate draft RESET forecasts from published CORR areas; no physics solve."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODELS = {"QS": "full_7c1820e764ee", "RR_QS": "full_5222212ebc04"}


def main():
    rows = []
    manifest = {r["path"]: r for r in json.loads((HERE / "INPUTS.json").read_text())["files"]}
    for model, case_id in MODELS.items():
        path = ROOT / "results/E002e_CORR_v001_r001/files" / (case_id + "_case.json")
        raw = path.read_bytes()
        relative = str(path.relative_to(ROOT))
        digest = hashlib.sha256(raw).hexdigest()
        if digest != manifest[relative]["sha256"]:
            raise ValueError("Published source identity mismatch: " + relative)
        case = json.loads(raw)
        result = case["result"]
        area = result["signed_area"]
        uncertainty = result["area_uncertainty"]
        rows.append({
            "model": model,
            "case_id": case_id,
            "source_file": relative,
            "source_sha256": digest,
            "A20": area,
            "u_A_engineering_not_tail_bound": uncertainty,
            "candidate_sign": "POSITIVE",
            "candidate_S_center": area,
            "candidate_S_scientific_band": [0.8 * area, 1.2 * area],
            "finite_rate_center_predictions": [
                {"gamma": gamma, "delta_F_center": gamma * area}
                for gamma in (0.001, 0.002)
            ],
        })
    output = {
        "status": "PROPOSAL_AWAITING_PEER_REVIEW_AND_USER_SCIENTIFIC_ACCEPTANCE",
        "not_a_frozen_launch": True,
        "input_report_commit": "5654dff87b3b7ca9b32ec2ce2a51454316c7ac78",
        "primary_model": "QS",
        "primary_hypothesis": "S_F_QS > 0",
        "gamma_grid": [0.0, 0.001, 0.002],
        "scientific_window_fraction": 0.20,
        "scientific_weak_regime_fraction": 0.10,
        "maximum_engineering_u_S": 1e-6,
        "maximum_engineering_u_delta_F": 1e-8,
        "models": rows,
        "new_physical_solutions": 0,
        "limitations": [
            "No infinite-tail bound follows from A20 or the final sample.",
            "Scientific acceptance bands are not numerical uncertainties.",
            "Finite-rate centers require both window transfer and a weak regime.",
            "No claim of quantum specificity, self-maintenance or free resources.",
        ],
    }
    (HERE / "proposal_predictions.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
