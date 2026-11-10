# X27_U010_V03 — Design Delta v0.5 (DRAFT)

**Status:** DESIGN_DRAFT / NOT_FROZEN / NOT_EXECUTED  
**Parent reference implementation:** v0.4.2  
**Purpose:** adjudicate audit findings and define the next specification before v0.4.3 code changes.  
**Scope:** X27-A and X27-B-LITE only. X27-B-FULL and X28 remain out of scope.

This document is a proposed design delta. It is not evidence that any mechanism operates in a physical system. No scientific main run is authorized by this document.

## 0. Version discipline

Separate the next work into two non-interchangeable deliverables:

- **v0.5 design delta:** changes the experimental object, oracle, policy family, repair semantics, resource domain, calibration and observables.
- **v0.4.3 implementation repair:** fixes defects in the existing v0.4.2 code and adds regression tests. It must not silently implement the v0.5 design.

After this document is accepted, implement v0.4.3 as a regression-only branch against the v0.4.2 manifest. Implement v0.5 semantics only in a subsequent implementation branch. Do not combine implementation repair with redesign in one commit or report.

## 1. P-register: classify assumptions rather than count them

Every model premise must be assigned to one of four classes.

| Class | Meaning | Required treatment |
|---|---|---|
| K | Formal substrate: finite state space, transition semantics, event ordering, deterministic/stochastic kernel | Declare explicitly; cannot be removed from a computational model |
| D | Design constants: costs, capacities, thresholds, initial resources, horizon, task definitions, repair rules | Freeze before the relevant run; perform declared sensitivity analysis |
| O | Observer choices: output profile, observation map, binning, H-Q observable | Freeze before evaluation; report sensitivity where meaningful |
| C | Directly outcome-stipulating or conclusion-equivalent assumptions | Remove from headline outcome definitions, or downgrade the claim |

The target is not an impossible global claim that C=0 for every part of the model. A finite model necessarily contains K-level transition rules. The operational requirement is:

    C_direct_output = 0

for headline performance outcomes: the kernel must not assign the success label merely because a source was read or an action was attempted. Success must be computed against an independent evaluator. Mechanisms encoded in the transition kernel remain explicit K/D assumptions and are not independent evidence for a physical mechanism.

Every result must be tagged as one of:

- MODEL_REALIZATION: the code realizes the declared mechanism.
- CONTROLLED_POLICY_COMPARISON: declared policies are compared on an independent task suite.
- PHYSICAL_MECHANISM_NOT_ESTABLISHED: default boundary statement for all X27 computation-only results.

## 2. F11 — Independent task oracle

### 2.1 Separation of task, memory and scoring

Introduce an independent task case:

    Q = (tau, p),   Y* = f_oracle(Q).

- Q is the task identifier and public input presented to D.
- f_oracle is a frozen evaluator table/function in the experiment manifest.
- Y* is the evaluator target and is not available to the executing policy.
- M_task and P_res are candidate information sources; neither defines the correct answer.

Use a balanced pair of task cases with different oracle targets. Cross the task cases with the full M_task × P_res factorial matrix. For each task case, both valid memory values remain possible interventions; a deliberately mismatched memory value is allowed to produce a wrong answer.

### 2.2 Distinct outcomes

Record at least:

    Y_readout = value actually returned by the selected read
    Y_function = operand/result actually used by the action
    Y* = f_oracle(Q)
    Y_correct = 1[Y_function = Y*]

Report these separately:

- Readout fidelity: returned value is transferred to the action operand as specified.
- Oracle correctness: action result equals the independent target.
- Causal source trace: the source-specific read precedes the action.
- Outcome profile: full joint profile including function, correctness, status, time and declared resource/apparatus outputs.

A correct answer without a source-specific read does not count as causal use of that source. A successful read that produces an oracle-wrong action is readout-faithful but task-incorrect.

H-M must no longer be defined as “all memory values are correct in all cells”. Its two components must be separately reported: causal readout of M_task, and task correctness against the oracle for each task/memory pairing. The expected treatment pattern must be specified per task case before running.

### 2.3 Oracle integrity

The oracle file must include task IDs, public inputs, target outputs, version, checksum and a declaration that target outputs are withheld from policy code. Test code must verify that the oracle module is not imported by policy implementation code. This is a software boundary check, not cryptographic proof against a malicious implementation.

## 3. F12 — Policy repertoire and selection

### 3.1 Fixed candidate library

Declare the following candidate policies:

| Policy | Allowed information path |
|---|---|
| pi_M | Read M_task, then use the returned value |
| pi_P | Read P_res, then use the returned value |
| pi_fixed | Emit a predeclared constant output |
| pi_none | Abstain / perform no read |
| pi_input | Use only the public task input p, without reading memory or payload |

The exact code, version and permitted input fields for every policy belong in the frozen manifest. Policies must not access Y*, the oracle table, held-out labels or hidden trace fields.

Keep the original fixed-policy run as a compatibility baseline. Do not replace the baseline result with whichever policy happens to score highest.

### 3.2 Capability versus selection

Report two different analyses:

1. Capability matrix: evaluate every candidate policy against every declared task and factorial cell.
2. Selection procedure: a predeclared selector may choose a policy using a separate validation suite, after which the selected policy is frozen and evaluated once on a disjoint held-out test suite.

The selector may not inspect held-out oracle targets. No policy may be selected and evaluated on the same examples for a headline test result. If no selector is implemented, report policy capability only and do not claim that D learned or selected a source.

A policy explicitly written to read M_task proves only the behavior of that policy. A policy-selection result is stronger only when the selection rule and held-out evaluation are independent. Both remain finite-model results, not proof of physical cognition.

## 4. F13 — Functionally distinct repair protocols

### 4.1 Apparatus health

Replace the current binary working/worn variable with a finite ordered health level:

    h in {0, 1, 2}

where 0 is non-operational, 1 is minimally operational and 2 is higher reserve health. The exact interpretation is operational and must be frozen.

For the reference repair contrast:

- A present A1/A2 starts at h=2.
- A successful Task 1 consumes one health level: 2 -> 1.
- Task 1 requires h >= 1.
- r0 restores h'=1.
- r1 restores h'=2.
- Both protocols have the same declared energy/material cost.
- Their byproducts are identical in the primary functional contrast. The artificial U+1 difference is removed from this contrast unless a separate physical conversion mechanism is specified and justified.

Task 2 has a declared apparatus load ell and succeeds only when h >= ell. The ordinary task uses ell=1. A separate, predeclared high-load diagnostic uses ell=2. Thus the R2 contrast is tested on an actual functional consequence:

- under ordinary load, both repairs may permit Task 2;
- under high load, r0 and r1 have different predicted outcomes.

The high-load diagnostic is not silently added to the existing R1 resource-stress set. It is a separate R2 functional validation.

### 4.2 R1 and R2 remain separate

- R1: fixed r0, no read of M_prod, internal restoration from inherited stock.
- R2: read M_prod; the returned instruction selects r0 or r1; verify that the action follows the read value and compare the functional response under the frozen load diagnostic.

R2 requires both a correct causal read/repair trace and a functional contrast. A resource-profile difference alone is insufficient. A full-profile TV may still be reported, but it cannot substitute for the functional criterion.

Include post-repair and post-Task-2 apparatus health in the B-LITE state/profile so the altered health transition is observable. State exactly whether a successful Task 2 causes a further health decrement; do not infer this after results.

## 5. F14 — Energy dose-response and robust threshold

### 5.1 Capacity correction

The proposed scan E_D^(0) in {1,2,3} cannot contain a robustly ready state under the current costs. In the R-int r0 baseline:

- Task 1 consumes one energy.
- Repair consumes one energy.
- Task 2 consumes one energy.
- omega_loss_E removes one additional energy immediately before Task 2.

Therefore:

    E_D^(0) >= 3 is required for nominal Task 2
    E_D^(0) >= 4 is required for Task 2 after omega_loss_E

With the current energy capacity of 3, robust success is impossible throughout the proposed dose range. Reporting an E* from {1,2,3} would therefore be mathematically invalid.

### 5.2 Proposed dose domain

Change the component-wise capacity to:

    R_max = (5,3,3,3).

Keep the primary baseline inherited stock unchanged:

    R_D^(0) = (3,2,0,0).

Run a separate exact dose sweep:

    E_D^(0) in {1,2,3,4,5},

holding material, waste, unavailable stock, controller, apparatus, repair rule, task costs and disturbance definitions fixed.

For the currently declared energy costs, the model-derived threshold is expected to be E*=4. This is a preregistered arithmetic expectation, not an observed result. The implementation must compute the threshold from all exact scenarios rather than hard-code 4.

Define:

    E* = min{E : V_rob(E)=1}.

If no tested E passes, return NO_ROBUST_THRESHOLD_IN_DOMAIN. If the exact sweep violates monotonicity, return MONOTONICITY_NOT_SUPPORTED and report the complete dose table; do not force a threshold summary.

Keep W_nom={omega_0} and W_stress={omega_delay,omega_loss_E,omega_loss_M}. Every stress case starts from an independent copy of the same post-repair snapshot.

## 6. F15 — Exact deterministic estimators, calibration and freeze artifacts

### 6.1 Exact thresholds

For the deterministic finite kernel:

- use exact rational probabilities (Fraction) for laws and contrasts;
- use epsilon_f=epsilon_P=0 where the criterion is exact equality;
- compute TV exactly;
- do not invent arbitrary MDE or significance thresholds for exhaustive deterministic enumeration.

For every distribution, reject negative, NaN or infinite probability mass and require exact normalization. Require:

    0 <= TV(P,Q) <= 1.

Apply the same validation to every transition law used by partition refinement. Stochastic extensions remain separate and require a preregistered MDE, error rates, power and multiplicity procedure.

### 6.2 A2 calibration must be computed

Replace the five hard-coded True calibration flags with a deterministic calibration procedure over a frozen calibration suite, separate from the main task/oracle test set.

The report must contain computed outcomes and supporting fingerprints for:

1. port compatibility;
2. functional equivalence on declared calibration probes;
3. transition equivalence on the calibration action set;
4. equal resource costs/byproducts;
5. connection under the frozen protocol.

A calibration result is valid only if every required test passes. The calibration suite and expected comparisons must be frozen before the main run. A2 calibration is a model-internal computed check, not a physical laboratory calibration.

### 6.3 P-register and oracle/policy artifacts

Add the following mandatory freeze artifacts:

- X27_P_REGISTER.yaml
- X27_ORACLE_TASKS.yaml
- X27_POLICY_LIBRARY.yaml
- X27_POLICY_SELECTION.yaml
- X27_A2_CALIBRATION_SUITE.yaml
- X27_REPAIR_HEALTH_DYNAMICS.yaml
- X27_ENERGY_DOSE_GRID.yaml
- X27_HQ_OBSERVABLES.yaml
- X27_HQ_INTERVENTION_SEQUENCES.yaml
- X27_CIRCULARITY_AUDIT.json

These supplement, rather than replace, the existing X27-A/B-LITE manifests, trace schema, operation costs, controls, exact closure and partition artifacts.

## 7. Mandatory v0.4.3 implementation repairs

The following are regression fixes against v0.4.2 and must be completed before implementing v0.5 semantics.

| ID | Defect | Required implementation/test |
|---|---|---|
| F1 | Empty stress set yields vacuous all() == True | Reject empty, duplicate and incomplete stress sets in the primary estimator; exact required set checked by protocol validation |
| F2 | State digest omits nested provenance fields | Canonical recursive serialization of all state dataclasses, including record creator_id, versions, IDs and all transition-relevant fields |
| F3 | H-A-token classification is one-directional | Report symmetric token-dependence direction separately from original-A1 necessity |
| F4 | TV and transition laws accept negative masses | Validate finite, nonnegative masses and normalization before computing TV/refinement |
| F5 | Task 1 checksum error becomes missing-read status | Preserve INTEGRITY_ERROR; reserve MISSING_READ_EVENT for absent read event; add a distinct NC |
| F6 | Delay event and read timestamp are ambiguous | Freeze delay-before-read semantics; add delay-start/end events; timestamp read after delay |
| F7 | PC7 compares only U rather than full TV | Build full R2 joint outcome profiles and call the same TV estimator; verify with an independent direct sum |
| F8 | Provenance logger emits C-production for A0/A2 | Emit object-specific provenance only when supported; distinguish C-created A1, test-fixture A2 and absent A0 |
| F9 | H-Q interpretation exceeds current observation map | Freeze exact O_t, distinguish predictive-output equivalence from full trace equivalence, and publish scoped partition labels |
| F10 | B-LITE H-Q merges R1/R2 contexts | Publish separate R1 and R2 partition results |

Required regression additions include:
- empty, incomplete and duplicate readiness scenario tests;
- mutation detection for each nested creator/provenance field;
- both directions of token mismatch;
- negative, non-finite and non-normalized TV/transition laws;
- Task 1 and Task 2 checksum corruption;
- exact delay event-time ordering;
- PC7 full-profile TV;
- A0/A1/A2 provenance event expectations;
- R1/R2 H-Q scope checks.

Add NC13_TASK_MEMORY_INTEGRITY_ERROR_DISTINCT_FROM_MISSING_READ. NC1 must test absence of the task-specific main-memory read only; a legal M_prod read must not satisfy it.

## 8. H-Q: exact scope and observations

The existing class counts 11 and 79 describe a selected decision-state domain, not all intervention-capable states.

Freeze the future observable as an explicit tuple. At minimum, functional outputs, correctness against the independent oracle, status, finish time, declared resource fields, apparatus health and pre-execution readiness outputs must be specified. The provenance/event journal remains a diagnostic trace unless a particular trace field is explicitly declared observable to D or to the evaluator.

Publish separate quantities:

- H-Q_task_decision: equivalence classes projected to sigma in {1,2,5,6}.
- H-Q_control_domain: equivalence classes over all intervention-capable states, including sigma=0,3, if the declared graph admits controls there.
- H-Q_R1: fixed repair protocol, no M_prod read/control.
- H-Q_R2: causal M_prod read/control.

The action alphabet, stage eligibility, no-op meaning of continue, repeat rules, combinations and depth limit must generate an explicit finite family of valid sequences. A command is applied at its eligible stage; commands are not silently queued. Terminal outputs remain leaves and are not partition members.

Do not call this full causal-trace equivalence. It is exact future-output equivalence under the frozen observable and intervention family.

## 9. v0.5 implementation acceptance

The v0.5 design is ready for implementation only after the owner accepts:

1. the oracle task cases and target table;
2. the policy candidate definitions and validation/test split;
3. the h in {0,1,2} repair semantics and high-load diagnostic;
4. the energy capacity and dose domain;
5. the computed A2 calibration suite;
6. the P-register and direct-circularity rule;
7. the H-Q observable and separate R1/R2 scopes.

No thresholds, task targets, policy selection outcomes, repair health levels or dose thresholds may be adjusted after inspecting the corresponding held-out results.

## 10. Current verdict

    X27:
      v0.4.2:
        package_reproducibility: AUDITED_BY_USER
        implementation_defects: OPEN
        github_source_publication: INCOMPLETE_UNTIL_ALL_SOURCE_PATHS_VERIFY
      v0.4.3:
        purpose: REGRESSION_REPAIR_ONLY
        status: NOT_IMPLEMENTED
      v0.5:
        purpose: ORACLE_POLICY_REPAIR_AND_DOSE_REDESIGN
        status: DESIGN_DRAFT
        not_frozen: true
      G7_MAIN_RUN: NOT_AUTHORIZED
      physical_mechanism: NOT_ESTABLISHED

The principal methodological change is that successful readout, oracle correctness, policy selection, functional repair and resource robustness become separately testable outputs. No single PASS flag may combine them.
