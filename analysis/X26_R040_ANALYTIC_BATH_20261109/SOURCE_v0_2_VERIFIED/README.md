# X26_R040_ANALYTIC_BATH — VM-ready conditional spectral package

**Code package status:** executable conditional R040 model and local tests.
**Scientific status:** not ADD-derived; no BIC has been found in the user's physical system.
**VM status:** prepared for later transfer; no target-VM calibration or submit has been performed.

## Integrated ADD–Phi–R040–Psi extension (v0.2.0)

The v0.2.0 source adds an **optional conditional pipeline** for the explicit interface postulates in `X26_MAPPING_POSTULATES.md`. It is not a derivation of a quantum Hamiltonian or loading reservoir from ADD.

- `x26r040.add_mapping`: verifies the pinned `carrier.py` Git blob, exports ordered local motifs, evaluates the declared local-density/local-barrier `Phi`, and emits a K-preserving motif-permutation control plus one actual `full_step`.
- `x26r040.loading`: driven coherent loading with signed, gross-input and recovered work channels.
- `x26r040.thermal_loading`: a separate detailed-balance Davies-type loading reservoir. It is a distinct postulate, not the scattering bath.
- `x26r040.resource_ledger`: explicit fuel, precursor, actuator, reset, heat and entropy bookkeeping; absent conversions/capacities stay `NOT_EVALUABLE`.
- `x26r040.transfer`: isometry and moving-projector intertwining tests for a separately declared `T_X`.
- `x26r040.integrated` / `x26r040.full_cli`: orchestration and fail-closed preflight for the complete conditional pipeline.
- `x26r040.workload_integrated`: declared operation inventory for runtime planning.

The new template `configs/X26_ADD_R040_LOADING.template.json` intentionally contains null or unaccepted inputs. The complete runner therefore blocks until the user explicitly accepts `Phi`, `Psi`, transfer and resource assumptions and supplies the carrier snapshot, role anchors and nested spectral manifest. No default parameter set is silently promoted to ADD-derived.

Run a fail-closed preflight:

```bash
PYTHONPATH=. python -m x26r040.full_cli \
  --manifest configs/X26_ADD_R040_LOADING.template.json \
  --outdir output/integrated-preflight --preflight-only
```

After supplying and freezing an accepted manifest, execute the same entry point without `--preflight-only`. The installed console command is `x26-r040-full`. This is a local runner only; it does not submit a VM job.

## What this package implements

1. The inherited three-mode R040 trimer in basis `(V,1,2)`.
2. An explicitly imported homogeneous 1D tight-binding bath coupled only to mode `2`.
3. Its analytic local Green function, causal physical branch, and adjacent second-sheet continuation.
4. Exact Feshbach/Schur reduction retaining the eliminated mode and bath through an energy-dependent `2x2` operator.
5. The continuous reduced spectral density **and** the discrete point-mass residues outside the bath band.
6. Direct BIC conditions separated from nonlinear second-sheet resonance poles.
7. Finite periodic-ring diagnostics with no invented irreversible finite-N width, plus the exact static no-loading projector check on the full finite trimer+ring Hamiltonian.
8. A separate driven-loading interface that requires an explicit control Hamiltonian and reports external work, while leaving actuator/reset/reservoir costs unevaluated without their models.
9. A standalone Fano line-shape control that never classifies its zero as a BIC.

It deliberately does not derive `H_d`, `V`, `W`, bath hopping, or the loading controller from `K1,K2` or from the ADD graph.

## Install and local tests

```bash
python -m pip install -r requirements.txt
PYTHONPATH=. python -m unittest discover -s tests -v
```

## Preflight

The frozen template contains null physical parameters and is expected to fail:

```bash
PYTHONPATH=. python -m x26r040.cli \
  --manifest configs/R040_SPECTRAL_INPUT.template.json \
  --outdir output/preflight --preflight-only
```

Exit code `2` is the correct blocking outcome. It must not be bypassed by setting source labels to `VALIDATED`; every parameter must have an explicit source class and evidence/assumption text, and model assumptions must be explicitly accepted.

## VM execution interface

After the model inputs, source classes, numerical grids, pole seeds, target-VM calibration and runtime forecast have been fixed and accepted, transfer this package at one fixed Git commit SHA to the VM using the repository's existing `infra/LAUNCH_RUNBOOK.md` route. Do not use this package to create a parallel VM submit mechanism.

The executable entry point after installation is:

```bash
./run_vm.sh /path/to/frozen_manifest.json /path/to/new_output_dir
```

`run_vm.sh` only runs the package in the environment where it is invoked. It does **not** submit to the VM queue. VM submission must use the existing project launcher and its source-digest/runtime gates.

## Input template and epistemic provenance

- `configs/R040_SPECTRAL_INPUT.template.json` is intentionally incomplete.
- `IMPORTED_ZERO_ROW.json` lists inherited ADD evidence, R040 conditional assumptions, the imported bath law, the missing ADD-to-local-Hamiltonian rule, and missing loading/resource inputs.
- `WORKLOAD_VOLUME.template.json` and `RUNTIME_GATE.template.json` are intentionally `NOT_EVALUABLE` until the manifest and target-VM calibration are frozen. A filled manifest emits exact declared operation counts, not a time forecast.

Allowed input provenance classes: `ADD_DERIVED`, `MODEL_ASSUMPTION`, `EXTERNAL_CALIBRATION`, `NOT_AVAILABLE`. Evidence hashes prove file identity, not the truth of its physical claims.

## Important interpretation constraints

- `BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL` means exactly that, not ADD-derived physics.
- A finite N ring is a closed Hermitian bath. It has a discrete spectrum and recurrences; the code never calls its finite-size eigenstate a continuum BIC.
- `J_eff(E)` is only the absolutely-continuous part of the reduced spectral measure. Q-block bound states appear as explicit point masses.
- The second-sheet pole equation and direct embedded-eigenvalue test are separate outputs.
- `x26r040.fano` is only a phenomenological line-shape control. A full multi-port Fano scattering observable requires a separately specified scattering background and ports.
- A driven loading calculation is a different protocol. `external_work_model_units` is not a complete actuator cost or thermodynamic resource ledger.

## Research lineage (not promoted)

Parents: R040/R041/R042, R105, R115, ADD carrier and K-revision. The package is a design/executable implementation for a conditional R040 spectral branch. It does not change the status of R040, R041, R042, R105, R115, L05, B09, R125 or NOW. No main scientific run is authorised or performed by this commit.
