# X27_U010_V03 — Regression Delta v0.4.3

**Status:** REGRESSION_CANDIDATE / SOFTWARE_VALIDATED / NOT_FROZEN / NOT_EXECUTED_AS_PHYSICAL_EXPERIMENT  
**Base:** v0.4.2 reference package  
**Rule:** no redesign of the experimental object; v0.5 decisions remain separate.

## Implemented repairs

| ID | Repair | Implementation contract |
|---|---|---|
| F1 | Readiness stress-set validation | The readiness estimator requires exactly `{omega_delay, omega_loss_E, omega_loss_M}`. Empty, duplicate, incomplete, extra and non-enum entries are rejected.
| F2 | Recursive state digest | Every dataclass field is serialized recursively, including nested provenance, IDs, versions, apparatus metadata, resources and all transition-state fields.
| F3 | Bidirectional token specificity | Reports token-original and token-substitute response directions separately from original-A1 necessity.
| F4 | Probability-law validation | TV and transition laws require non-empty normalized distributions with non-negative exact `int`/`Fraction` masses. `float` and `bool` are rejected.
| F5 | Integrity status preservation | A checksum-invalid Task-1 record yields `INTEGRITY_ERROR`; an absent read event yields `MISSING_READ_EVENT`. A legal M_prod read does not substitute for M_task.
| F6 | Delay/read ordering | Delay start and end are distinct time-stamped events. Task-2 read and operand binding occur only after delay completion.
| F7 | Full PC7 profile contrast | PC7 computes TV over the complete joint R2 outcome profile, then checks it against a separate direct sum over the union support. The report publishes the differing profile/resource fields; the v0.4.2 contrast still differs only in `R_final.U`, so no functional-outcome difference is claimed.
| F8 | Object-specific provenance | C production/transfer events are emitted only for C-attributed A1. A2 is fixture-attributed; A0 is recorded as absent. Non-C-created records are not attributed to C.
| F9 | H-Q claim scope | The output declares O_D, O_eval and J_trace separately, excludes the diagnostic event journal from partition observations, and explicitly disclaims full causal-trace equivalence.
| F10 | Legacy H-Q context | B-LITE H-Q is labelled `LEGACY_R2_LIKE_CAUSAL_M_PROD_READ`; it is not treated as R1 and the historical class count is not a frozen result.

## Negative controls

- **NC13 — nested-state side-channel detection:** on disposable stage-4 snapshots, mutation of nested record provenance/identity fields and apparatus provenance/identity must change the digest and yield `RUN_INVALID_SIDE_CHANNEL_LEAK`.
- **NC14 — integrity versus missing read:** corrupted memory and absent read event must remain distinct in the resulting statuses. This keeps the earlier `NC13_TASK_MEMORY_INTEGRITY_ERROR_DISTINCT_FROM_MISSING_READ` request from colliding with the subsequently specified NC13 side-channel definition.

## Explicitly not included

This branch does not implement F11–F14 or the v0.5 design: no independent task oracle, policy-selection design, tri-level apparatus health, high-load repair contrast, component capacity `(5,3,3,3)`, energy dose sweep, or A2 computed-calibration redesign. Resource capacity remains 3; apparatus health remains the original binary working/worn state.

## Validation boundary

Unit tests, exact estimators, controls, reachability closure and H-Q reproduction are software-only results. The legacy H-Q counts remain diagnostic reproduction metadata and are not promoted to frozen H-Q findings. Nothing here establishes a physical X27 mechanism or authorizes G7.
