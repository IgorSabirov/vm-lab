"""Document metadata and draft thresholds only; no physical computation."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = ROOT / "analysis/E002e_CORR_MECHANISM_v001"


def main():
    path = PREVIOUS / "proposal_predictions.json"
    raw = path.read_bytes()
    manifest = json.loads((PREVIOUS / "PUBLICATION_MANIFEST.json").read_text())
    record = next(r for r in manifest["files"] if r["path"] == str(path.relative_to(ROOT)))
    if hashlib.sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("Historical prediction source changed")
    data = json.loads(raw)
    data.update(
        proposal_version="E002e_RESET_v002",
        status="REVISED_CONCEPT_AWAITING_USER_SCIENTIFIC_ACCEPTANCE_NOT_FROZEN",
        predecessor_commit="73f9f14958abaab160de35339714311edb382344",
        predecessor_prediction_sha256=record["sha256"],
        relative_test_guard=dict(signal_to_uncertainty_factor=10.0,
                                 S_absolute_floor=1e-6, A20_absolute_floor=1e-6),
        interval_rule=dict(
            form="abs(x-y) <= alpha*abs(z)",
            supported="abs(x-y)+ux+uy <= alpha*max(0,abs(z)-uz)",
            refuted="max(0,abs(x-y)-ux-uy) > alpha*(abs(z)+uz)",
            otherwise="UNRESOLVED",
            interpretation="CONSERVATIVE_ENGINEERING_INTERVALS_NOT_STATISTICAL_COVERAGE"),
        tail=dict(value="S_F - A20", uncertainty="u_S + u_A",
                  not_a_decay_time=True, not_a_spectral_width=True),
        energy_per_event="Tr(H*(R_E(rho_gamma)-rho_gamma))",
        scientific_tasks=dict(NESS=6, response_RHS=2, methods=2,
                              task_solves=16, internal_backsolves_counted_separately=True),
    )
    (HERE / "proposal_predictions_v002.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

    proof = dict(
        status="ANALYTIC_EXTENSION_OF_PUBLISHED_CERTIFICATE_NOT_NEW_NUMERICAL_CHECK",
        models=["QS", "RR_QS"], v=1.0, gamma="ALL_FINITE_GAMMA_GE_ZERO",
        phi_over_pi=0.5, epsilon=0.0, node_noise=0.05,
        source_commit="73f9f14958abaab160de35339714311edb382344",
        prior_certificate="analysis/E002e_NEIGHBOR_REVIEW_20261101/uniqueness.json",
        prior_certificate_sha256=hashlib.sha256((ROOT / "analysis/E002e_NEIGHBOR_REVIEW_20261101/uniqueness.json").read_bytes()).hexdigest(),
        proof="DERIVATIONS.md sections 1-5",
        premises=[
            "Six nonzero dephasing jumps generate all 216 diagonal rank-one projectors.",
            "Restored m6 hopping12 support cannot cancel old graph edges.",
            "Original jumps remain unchanged.",
            "Full reset Kraus sum is identity, so H_eff changes by -i*gamma*I/2.",
            "tau_E is fixed, PSD and trace one.",
        ],
        conclusion="UNIQUE_FAITHFUL_RELAXING_NESS_FOR_THIS_OPERATOR_FAMILY",
        no_numerical_gap_bound=True, numerical_operator_recheck_required_in_future_runner=True,
        new_Liouvillians=0, new_NESS=0,
    )
    (HERE / "uniqueness_scope_v1.json").write_text(
        json.dumps(proof, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
