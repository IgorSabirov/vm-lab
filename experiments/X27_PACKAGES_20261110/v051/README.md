# X27_U010_V03 — v0.5.1 Oracle / Policy / Repair / Dose Reference Model

**Version:** `0.5.1`  
**Status:** `DESIGN_DRAFT / NOT_FROZEN / MAIN_RUN_NOT_EXECUTED`  
**Validation:** software smoke only  
**Physical mechanism:** not established

This is a **new experimental model**, not a silent patch of v0.4.3. The v0.4.3 regression ZIP is retained as a separate baseline reference; the uploaded archive was executed before this implementation and its 41 tests passed. See `REGRESSION_BASELINE_v043.md`.

## Install and reproduce

Python 3.10+, standard library only.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q src tests
x27v051 smoke --output validation
```

Without installation:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m compileall -q src tests
PYTHONPATH=src python -m x27v051.cli smoke --output validation
```

## Implemented model

### D1 — independent oracle

- Evaluator task cases live in `x27v051.oracle`. The execution transition kernel `engine.py` does not import `oracle.py` or `evaluation.py`, has no evaluator-key/target/tau fields, and `run_b_lite()` has no evaluator parameter.
- `evaluation.py` is the evaluator-side composition layer: it joins the hidden evaluator case to an already-produced execution result and computes `Y_correct` afterwards. Oracle correctness is absent from `BState`, `Task2Result`, readiness and resource transitions.
- The oracle computes `Y* = f_oracle(tau, p)`. The executor receives only `p` as `public_input`; it never receives `tau`, evaluator key, opaque identifier, oracle target, state, resource vector or trace.
- Memory/payload values are not placed in the observation in advance. A policy must explicitly call its granted `read_task_memory()` or `read_residual_payload()` capability; that call creates the source-specific read event. A policy cannot call the ungranted source capability. The causal validator binds record ID, version and creator ID across provenance, transfer, receipt, source-off, read and action.
- The two challenge cases have identical public input and different evaluator-only targets (0/1). This tests a controlled information bottleneck. It is not a general task suite. Because `public_hint` is fixed to 0, `pi_fixed` and `pi_input` are behaviorally identical in this specific challenge; this redundancy is an explicit limitation, not evidence of distinct policy capability.
- Each matrix row separates `readout_value`, `action_operand`, `Y_action`, `Y_correct`, `readout_fidelity`, source-specific read trace and status. Memory/payload alignment with the oracle target is independently computed from `f_oracle(tau,p)`.
- The causal-use validator checks matching `record_id` and `version` across producer provenance, transfer, D receipt/accessibility, `source_off`, source-specific read and action binding. It rejects a read from a different record even when a generic read/action sequence is present.
- Task 1 and Task 2 in B-LITE also record `Y_action` and `Y_correct` independently from the mechanical execution status. A task can execute successfully while producing an oracle-incorrect answer.

### D2 — candidate policy repertoire

The 40-row factorial capability matrix consists of 2 evaluator cases × 5 candidate policies × 4 `(M_task,P_res)` cells. Candidate policies are `pi_M`, `pi_P`, `pi_fixed`, `pi_none`, and `pi_input`. The legacy `pi_0_legacy` memory readout is evaluated separately and does not inflate the 40-cell matrix. Policy selection is `CAPABILITY_ONLY`; no validation/test selector is claimed. `pi_fixed` and `pi_input` emit the same value in this particular challenge because `public_hint` is always 0; the current task set therefore does not demonstrate a distinct public-input-only behavior. B-LITE retains a fixed, explicit M_task readout controller for the repair/readiness experiment; it is not a policy-selection experiment and does not use the five-policy capability matrix to choose its controller.

### D3/D4 — health and functional R2

Apparatus health is `h∈{0,1,2}`. Task 1 changes `2→1`; `r0` sets `h'=1`; `r1` sets `h'=2`; successful Task 2 decrements health by one. Task 2 success is the conjunction of valid memory read, adequate health, resources and time.

Exact functional contrasts:

| Task 2 load | r0 | r1 | `TV_func` | `TV_state_profile` |
|---|---|---|---:|---:|
| `ell=1` | SUCCESS, final h=0 | SUCCESS, final h=1 | 0 | 1 |
| `ell=2` | APPARATUS_DEGRADED | SUCCESS, final h=1 | 1 | 1 |

R2 requires `TV_func(ell=2)=1`, `TV_func(ell=1)=0`, and a causal `M_prod` read→repair-action trace. TV_state_profile is the predeclared evaluator-visible post-task profile (execution/status/action, final health, finish time, resources), not the complete hidden Markov state. It is diagnostic only; full hidden-state TV is not computed.

**Important limitation:** after Task 1 leaves `h=1`, `r0` sets `h'=1`; therefore its health gain is zero. At ordinary load 1, R0 without any repair also succeeds. The smoke report explicitly returns `R1_FUNCTIONAL_BENEFIT=NOT_DEMONSTRATED_FOR_r0_UNDER_D3_RULES`. In the reference dose-3 comparison, no-repair R0 also succeeds at load 1 and has `V_rob=1`, while repaired R_int/r0 has `V_rob=0` because it spends the energy reserve that R0 retains. Thus this model does not show a functional benefit of r0; under the selected resource costs it can reduce robustness. No extra wear event is invented to force an R1 PASS. The design owner must resolve this before freeze if R1 is intended to demonstrate a functional repair benefit.

### D5 — component resources and dose response

Capacity is `(4,3,3,3)` and the initial dose is `R_D^(0)(E)=(E,2,0,0)`, `E∈{1,2,3,4}`. Costs/byproducts:

| Operation | Cost `(E,M,W,U)` | Byproduct `(E,M,W,U)` |
|---|---:|---:|
| Read Task 1 / 2 | `(0,0,0,0)` | `(0,0,0,0)` |
| Task 1 / 2 | `(1,0,0,0)` | `(0,0,1,0)` |
| Repair r0 / r1 | `(1,1,0,0)` | `(0,0,1,0)` |
| External injection | Inflow `(1,1,0,0)` | — |

The single component-capacity function is used by every operation. Resource mutation order is inflow → cap/spill → atomic cost check → deduction → byproduct → cap/spill. The exact R-int/r0 sweep computes nominal threshold 3 and robust threshold 4 from the defined stress set. The thresholds are not hard-coded into the estimator.

### D6 — exact arithmetic

Only integer and `Fraction` probability masses are accepted. Booleans, floats, negative masses, empty and unnormalized distributions are rejected. TV uses exact arithmetic and an independent direct-sum check verifies support-union calculation.

### D7 — H-Q

- `O_D`, `O_eval`, and diagnostic `J_trace` are separate.
- The intervention alphabet is stage-qualified, non-queued and limited to two interventions.
- Every generated complete schedule explicitly advances through stages 0–6 with one `continue@stage_k` token per stage. Same-stage interventions may co-occur only on distinct controlled variables; contradictory duplicate controls are excluded.
- The exact partition-refinement algorithm is implemented and unit-tested.
- **The complete v0.5.1 model adapter and four published H-Q partitions (task/control/R1/R2) are not yet independently validated.** The report labels them `NOT_EVALUATED_ADAPTER_PENDING`; the generic algorithm test is not represented as a model H-Q PASS.

## Software boundary tests

The static audit checks both sides of the boundary: production policies do not import oracle/engine/state modules; the executor engine does not import oracle/evaluation modules or contain evaluator identifiers; and `run_b_lite()` has no evaluator argument. Runtime probes block evaluator-only fields and ungranted source capabilities. This is architectural separation against accidental access in the declared code path, **not** process isolation against arbitrary hostile Python. `evaluation.py` is explicitly evaluator-side and may import both the oracle and execution result types.

## Additional controls

- NC13: digest immediately before/after readiness estimator call, including nested provenance fields; deliberate nested mutation must change the digest.
- NC15: 200 unique opaque identifiers, fixed RNG seed `51015`, balanced targets 100/100, exact 100/200 accuracy for input-only baseline and action invariance under ID relabelling. This is a deterministic balanced-design control, not a statistical generalization estimate.
- NC16: static policy AST/import audit and runtime probes for oracle, evaluator ID, target, state, resources, trace and production-memory fields. It is an accidental-access guard, not a secure sandbox for arbitrary hostile Python.
- A2 calibration is computed against declared fixture probes, not assigned as unconditional `True` flags. It remains a model-internal calibration, not a physical lab calibration.

## Outputs

`x27v051 smoke --output validation` generates:

- `CAPABILITY_MATRIX.csv` — 40 factorial rows (2 evaluator-only task cases × 5 candidate policies × 4 M×P cells; A1 held fixed);
- `CAPABILITY_FACTORIAL_CONTRASTS.json` — exact full-joint-profile M/P TV contrasts per evaluator case and candidate policy;
- `APPARATUS_CLASS_CONTRAST.json` — A0/A1/A2 class necessity contrast with public-input-only probe and apparatus-use/provenance traces;
- `PI0_LEGACY_BASELINE.csv` — separate compatibility baseline;
- `NC13_RESULTS.json`, `NC15_RESULTS.json`, `NC16_RESULTS.json`;
- `NC14` integrity-vs-missing-read check is included in `NEGATIVE_CONTROLS.json`;
- `A2_CALIBRATION_RESULTS.json`, `E2_EXACT_VALIDATION.json`;
- `DOSE_SWEEP.json`, `R2_FUNCTIONAL_CONTRAST.json`, `R1_FUNCTIONAL_LIMITATION.json`;
- `HQ_INTERVENTION_SEQUENCES.json`, `HQ_OBSERVABLES.json`;
- positive/negative controls, `SMOKE_REPORT.json` and `SHA256SUMS.txt`.

See also [`SCOPE_LIMITATIONS_v051.md`](SCOPE_LIMITATIONS_v051.md) for explicit interpretation boundaries, especially the unresolved R1 functional-benefit issue.

## Freeze blockers

Current checked source build: **42/42 unit tests passed**, `compileall` PASS, and the fresh `smoke` report marks `software_smoke_pass=true`. The smoke build is not a scientific main run. Before `DESIGN_FROZEN` and G7, the project still needs:

1. owner decision on the R1 zero-health-gain/repair-necessity limitation;
2. independent review of oracle task semantics and target table;
3. full H-Q transition adapter and four separate model partitions;
4. exact G0 reachable closure for the complete frozen intervention kernel;
5. independent source/manifest audit and reproducible hash freeze.

X27-B-FULL recycling, resource reproduction, D2, new-record creation/R063 and X28 are not implemented here. Producer C production/transfer remains trusted prehistory. All PASS results are software-model properties, not evidence of a physical mechanism.
