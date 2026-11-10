# X27 v0.4.2 — implementation decisions and scope delta

**Status:** reference implementation / software validation only; `DESIGN_DRAFT`, `NOT_FROZEN`, `MAIN_RUN_NOT_EXECUTED`.

This note lists executable choices needed to turn the v0.4.1 hotfix plan into a finite Python model. It does not claim that these choices have been physically established or that the protocol has received final scientific acceptance.

## Implemented corrections

1. **Readiness isolation.** State and resource objects are frozen dataclasses. Each readiness scenario is simulated from its own deep-copied stage-4 snapshot. All scenarios are evaluated before aggregation; the reverse-order pass is also computed. State digests are compared before and after estimation. NC10–NC12 test mutation, order dependence and scenario completeness.
2. **Task 2 is explicit.** Stages are `0..7`; Task 2 is read at stage 5, executed at stage 6 and recorded at stage 7. Time is independent of stage and the delay scenario consumes one additional time unit.
3. **Independent X27-A/B profiles.** X27-A contains only Task 1 profile and post-Task-1 resources. X27-B-LITE contains Task 2, readiness diagnostics and post-Task-2 resources.
4. **Producer C is exogenous prehistory.** C write/production/transfer events are provenance facts in the trace. They are not simulated and their costs are not charged to D.
5. **Resources.** All costs are nonnegative and deducted atomically after inflow/spill. Byproducts are credited after cost deduction and capacity-checked. Failed atomic cost checks do not partially deduct or credit byproducts.
6. **H-Q domain.** Operational helper stages are retained internally so future transitions are exact. Public equivalence classes are restricted to decision stages `σ∈{1,2,5,6}`. Terminal states are outcome leaves, not partition members. The earlier all-node partition counts are superseded.

## Explicit modeling choices (not deductions)

- Checksum rule: `h(s)=1-s`.
- Task 2 repeats the original `M_task`; it does not request a new record.
- **R1 uses a fixed, preregistered `r0` repair protocol and does not read `M_prod`.** This makes R1 an internal-repair test without presupposing R2.
- **R2 separately reads `M_prod` and selects `r0` or `r1`.** The two valid instructions differ in the byproduct profile: `r1` deposits one unit in the unavailable `U` component.
- `R_ext` injects `(1,1,0,0)` after Task 1 and before repair, then performs the default `r0` repair. It is intentionally not cost-matched to `R_int`.
- The Task 2 horizon checks both the stage-5 read/delay deadline and the stage-6 final execution step; an over-horizon action is not performed and does not consume its resources.
- The task result equals the bit read from `M_task`; Task 1 consumes one energy and produces one waste; Task 2 has the same cost.
- A successful Task 1 changes apparatus health to `worn`; successful repair restores health to `working`.
- Default H-A-token result is `NOT_CLAIMED`, because the baseline kernel does not read apparatus identity as a dynamic variable.
- H-Q interventions are stage-local, not queued. No more than two `do(...)` interventions are allowed per path; `continue` advances one stage.
- H-Q baseline context is `R_int / omega_0`. G0 closure is broader and includes all restoration arms and disturbance contexts.

## Current exact software diagnostics

See `validation/smoke_report.json` and its sidecars. The current reference build reports:

- 22/22 unit tests pass.
- G0 reachable physical states: X27-A 132; X27-B-LITE 6,752 (limit 350,000).
- H-Q: 11 decision-domain predictive classes for X27-A and 79 for X27-B-LITE; terminal outcomes are output leaves.
- E2 6/6; positive controls 9/9; negative controls 12/12.
- R1 (`R_int`, fixed `r0`): nominal pass, robust fail due to `omega_loss_E`.
- R2 (`M_prod`-causal `r0/r1`): both execute Task 2; final `U` differs by one unit; deterministic full-profile TV is 1.

These are properties of this particular code and manifest. They do not constitute evidence for a physical mechanism, do not validate the assumptions independently, and do not authorize G7.
