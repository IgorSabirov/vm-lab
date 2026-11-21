# X26 integrated extension v0.2.0

This release adds the optional ADD-to-R040 interface pipeline on top of the v0.1 conditional spectral package.

## Included implementation

- Explicit `MODEL_ASSUMPTION`-gated local motif mapping `Phi`.
- Pinned `carrier.py` source verification by Git blob SHA-1.
- Local motif feature extraction, exact combinatorial K1/K2 reporting, K-preserving permutation sensitivity control, and one real ADD `full_step` with anchor transport.
- Direct BIC checks before and after that carrier step.
- Reuse of the v0.1 exact spectral runner with the mapped pre-step parameters, after its independent fail-closed preflight.
- Coherent driven loading and a separate thermal/Davies loading protocol.
- Explicit resource ledger with no inferred conversion from bit counts to fuel.
- Moving-projector/isometry test with externally declared `T_X`.
- Integrated fail-closed CLI and workload inventory.

## Epistemic status

`CONDITIONAL_PHI_PSI_MODEL_NOT_ADD_DERIVED`. The local mapping, loading mechanism, transfer operator and resource conversion are postulates, not consequences of K1/K2. The supplied template has null/unaccepted assumptions. No physical calibration, VM calibration or VM submission is included in this source publication.

## Run

```bash
python -m pip install -r requirements.txt
PYTHONPATH=. python -m x26r040.full_cli \\
  --manifest configs/X26_ADD_R040_LOADING.template.json \\
  --outdir output/preflight --preflight-only
```

Exit code 2 is the expected fail-closed outcome for the untouched template. A model run requires a separately frozen manifest with all assumptions explicitly accepted.

## Scope limitation

The coherent and thermal loaders evolve the declared three-mode subsystem under their stated control/reservoir postulates. The external resource model remains a separate required input. The moving-projector test only checks the declared finite-dimensional map; a one-step pass is not a proof of global protection on an infinite growing carrier.
