# Integration with the vm-lab VM route

This repository package is an experiment payload, not a queue launcher.
`run_vm.sh` executes locally in the environment where it is called; it does not
submit a VM job, choose a queue, or bypass the project's runtime gate.

Before any main execution:

1. Select and explicitly accept the conditional R040 + 1D tight-binding bath
   model, or provide a different physically motivated model in a new branch.
   The parameters are not inferred from ADD `K1/K2`.
2. Freeze all model parameters, provenance records, ring sizes, complex test
   points, pole seeds, numerical tolerances, and the model assumptions document.
3. For every `ADD_DERIVED` or `EXTERNAL_CALIBRATION` input, include a stable
   evidence reference and SHA-256. A digest establishes file identity only; it
   does not prove the scientific claim.
4. Run the local tests and blocking preflight. The template is expected to
   return exit code 2. Do not alter provenance labels to evade this result.
5. Compute the code/manifest digest from the frozen checkout. Build the
   workload inventory from that manifest. It is an operation inventory, not a
   runtime forecast.
6. Measure a representative calibration of this exact package and workload on
   the target VM. Record environment fingerprint, calibration/forecast hashes,
   central estimate, range, hard wall, RAM and disk limits in the runtime gate.
7. Follow the existing repository `infra/LAUNCH_RUNBOOK.md` for fixed-SHA
   packaging, delivery, runtime-gate review, and any authorized submit. Do not
   add a parallel launcher or edit code directly on the VM.

The package has no automatic permission to submit. Its default manifest is
intentionally incomplete and `submit_allowed=false`. Loading is a separate
protocol; turning `loading.enabled` on blocks this spectral-only executor.

## Output interpretation

- `BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL` is a result only under the
  declared trimer, one-port geometry, and tight-binding bath assumptions.
- `SECOND_SHEET_RESONANCE` is a distinct lower-half-plane pole result.
- The Fano helper is a line-shape control, not a multi-port transport solver.
- Finite rings are closed systems; their irreversible width is always null.
- `TECHNICAL_CHECKS_PASS_CONDITIONAL_R040_MODEL` means code-level checks passed
  for the frozen conditional model. It is not ADD-derived evidence or promotion
  of R040/R041/R042/R105/R115/L05/B09/X10.
