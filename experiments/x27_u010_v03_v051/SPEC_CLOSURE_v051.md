# X27 v0.5.1 — Specification closure record

Status: `DESIGN_DRAFT / NOT_FROZEN / NOT_EXECUTED`. This record documents the current decisions; final acceptance and the independent audit are still required.

## D1 — Independent oracle

The executor receives only public task input (p), not task ID or target:

[
Q_{eval}=(\tau,p),\qquad I_D=p,\qquad Y^*=f_{oracle}(Q_{eval}).
]

The evaluator joins the hidden task case only after policy execution. The model stores separate fields for the value read, action operand, actual action result (Y_{action}), and correctness (Y_{correct}=1[Y_{action}=Y^*]). Policy code has no oracle import or target field. Static import checks and runtime access probes are guardrails, not a secure sandbox against hostile Python.

## D2 — Capability-only policies

The five policies are `pi_M`, `pi_P`, `pi_fixed`, `pi_none` and `pi_input`. Legacy `pi0` remains a separate compatibility baseline. The current scope is `CAPABILITY_ONLY`; no selector or independent policy-learning claim is made.

The capability design is 2 oracle task cases × 5 policies × 4 M/P cells = 40 cases. For each case, the report separates readout fidelity, action result, oracle correctness, status and declared resources.

## D3/D4 — Apparatus health and R2

Health is (h\in\{0,1,2\}), initialized at 2. Successful Task 1 decrements health by one. Repair (r_0) restores (h'=1); (r_1) restores (h'=2), with equal primary resource costs and no artificial U increment. Successful Task 2 decrements health by one.

Task 2 success is conjunctive:

[
Y_{T2}=G_{memory}\land G_{health}\land G_{resource}\land G_{time}.
]

The functional load is (ell\in\{1,2\}). Primary R2 criterion uses (ell=2): (r_0) fails and (r_1) succeeds in the current model, so exact (TV_{func}=1). At (ell=1), both protocols succeed, (TV_{func}=0); however, the final health differs after the Task 2 decrement, so the full state-profile TV is 1. These are distinct metrics; (TV_{state}(\ell=1)) is diagnostic only and cannot qualify R2.

R2 PASS requires the source-specific M_prod read, read-to-repair causal trace, and the predeclared high-load functional contrast. A resource-profile difference alone is insufficient.

## D5 — Resource capacity and dose

[
C=(4,3,3,3),\qquad R_D^{(0)}(E)=(E,2,0,0),\qquad E\in\{1,2,3,4\}.
]

Task 1, repair and Task 2 each cost one energy; repair also costs one material. Reads cost zero. Therefore the exact expected thresholds are:

[
E^*_{nominal}=3,\qquad E^*_{robust}=4.
]

These are arithmetic consequences of the declared operation costs and stress set, not observed physical thresholds. The code must compute the table by exhaustive enumeration; it must not hard-code the result. External-resource arm comparisons remain resource-imbalanced and cannot be interpreted as an efficiency comparison.

## D6 — Exact arithmetic

Probability laws accept only finite nonnegative integers or rational `Fraction` masses, with exact normalization. Floating-point probability masses, negative masses and invalid transition laws are rejected. Total variation is exact:

[
TV(P,Q)=\frac12\sum_{x\in supp(P)\cup supp(Q)}|P(x)-Q(x)|.
]

A direct independent sum is used as a cross-check.

## D7 — H-Q information levels

Three information channels stay separate:
- (O_D): observations available to the executor;
- (O_{eval}): evaluator observations and outcome fields;
- (J_{trace}): diagnostic append-only journal.

The planned outputs are H-Q-task, H-Q-control, H-Q-R1 and H-Q-R2, with all valid intervention sequences enumerated to depth two. The current implementation contains exact finite partition-refinement machinery and schedule generation, but the complete v0.5.1 model adapter is not yet accepted. No H-Q PASS is claimed. Previous v0.4.2 class counts 11 and 79 are not inherited.

## NC13 / NC15 / NC16

- **NC13:** compare canonical state digests immediately before and after each estimator call. Do not compare different legitimate lifecycle stages. Include nested provenance identifiers and creator fields.
- **NC15:** static interface exclusion of task ID plus 200 deterministic opaque-ID presentations with frozen seed, balanced expected accuracy 100/200 = 0.5 for an ID-ignorant policy, and invariance under reassigning opaque identifiers. This checks the constructed deterministic control, not general statistical inference from two tasks.
- **NC16:** static AST/import dependency checks plus runtime whitelist probes for forbidden oracle and evaluator fields. This is an architectural regression control, not OS-level sandbox security.

## Non-goals

This model does not simulate C's production/transfer process, does not establish physical causality, does not establish a complete resource-reproduction cycle, does not create a new Task 2 memory record, does not implement X27-B-FULL, D2, or X28. The scientific main run G7 remains blocked.
