# X27 v0.5.1 — Specification closure record (draft)

**Status:** `DESIGN_DRAFT / NOT_FROZEN / NOT_EXECUTED`  
**Purpose:** record the implemented interpretation of D1–D7 and the unresolved conditions that block freeze/G7.

## 1. Oracle and task interface

The oracle computes `Y*=f_oracle(tau,p)` for evaluator-side `Q_eval=(tau,p)`. The executor receives only `I_D=p` as `public_input`; memory and payload are available only through explicit, policy-specific read capabilities. It does not receive `tau`, an evaluator task key, an opaque identifier, the oracle target, the state object, or the trace journal.

The two evaluator task cases have **identical public input** and different hidden evaluator contexts `tau` (A/B), with oracle targets 0 and 1. The oracle table is keyed by `(tau,p)`, not by an opaque task identifier. This is intentional: an input-only policy cannot distinguish the evaluator cases from the current public input; an eligible source value can determine its action, and oracle correctness is then scored independently. This is a deliberately narrow capability challenge, not a claim that all real tasks should hide their semantic type.

The policy API exposes `public_input` plus source capability methods. For candidate-policy traces, record ID, version and creator ID are bound across provenance, transfer, D receipt, source-off, read and action. A policy must call `read_task_memory()` or `read_residual_payload()` to cause the corresponding read; only the policy's granted source capability is callable. The source value is not preloaded into an observation field. The five-candidate capability matrix is exactly 2 evaluator tasks × 5 candidate policies × 4 M×P cells = 40 rows, with A1 fixed. The old `pi_0` readout is retained as a separate compatibility baseline and is not counted among the five candidates.

## 2. D1 outcome separation

Each capability row records:

- `readout_value`: value returned by the selected source read, or null when no read occurs;
- `action_operand`: value actually delivered to the action, or null on abstention;
- `Y_action`: actual emitted binary answer, or null on abstention;
- `Y_correct`: null on abstention; otherwise exact equality with independent `Y*`;
- `readout_fidelity`: whether a source read was transferred unchanged to the action operand;
- `causal_source_use`: the same record ID/version is present in provenance, transfer, D receipt/accessibility, source-off, source-specific read and action binding; the returned value equals the action operand. A generic read/action adjacency is insufficient.

The oracle module imports no policy, engine, or state module. Policy code never imports the oracle. The execution transition kernel `engine.py` also does not import `oracle.py` or `evaluation.py`, exposes no evaluator key/target/tau fields and does not accept an evaluator key in `run_b_lite()`. The evaluator-side `evaluation.py` joins the hidden evaluator context to an already-produced action after execution and is the only production layer allowed to combine the oracle target with an execution result. The import/AST audit and runtime forbidden-field/source-capability probes are accidental-access controls, not a security boundary against arbitrary hostile Python; hostile extensions require process-level sandboxing.

## 3. NC14, NC15 and NC16

NC14 checks that checksum corruption for Task 1 and Task 2 remains `INTEGRITY_ERROR`, while `MISSING_READ_EVENT` is reserved for a missing task-specific read. A legal `M_prod` repair read cannot satisfy the `M_task` causal-read requirement.

NC15 uses seed `51015`, 200 unique opaque evaluator identifiers, and exactly 100 target-0 / 100 target-1 presentations. `pi_input` receives the same public input on every presentation and cannot receive identifiers. Its deterministic action is invariant under an independently permuted identifier assignment and gives exactly 100/200 correct. This exact 0.5 is a balanced deterministic control, not a statistical estimate of generalization error or a confidence bound.

NC16 checks policy imports and forbidden source references statically, then probes the runtime context for `oracle`, `task_id`, `evaluator_key`, `target`, `state`, `resources`, `trace`, and `prod_memory`. All attempts must be blocked and logged.

NC13 compares the complete recursive state digest immediately before and after the readiness-estimator call. A separate adversarial nested `creator_id` mutation must change the digest. It does not compare states across legitimate stage transitions.

## 4. Apparatus class comparison

The 40-cell memory/payload capability matrix holds A1 fixed, as preregistered. A separate A0/A1/A2 class contrast was added so the prior H-A-class question is not silently dropped. To avoid circularity, the hardware probe uses `pi_input` and its public-input output (0) as the action operand in both evaluator cases. The hidden evaluator target is scored separately; in case B this probe is deliberately oracle-incorrect, but that does not determine whether the apparatus allowed the operation. The H-A-class test contains no `M_task` read and does not claim memory use. A0 must block the operation without apparatus-use event; A1 and computed-calibrated A2 must perform it and emit use events; exact TV is 1 for A1-vs-A0 and A2-vs-A0 and 0 for A1-vs-A2. `H-A-token` remains `NOT_CLAIMED`. These are computed fixture results, not physical apparatus evidence.

## 5. D3/D4 repair interpretation and the R1 limitation

Health is `h∈{0,1,2}`. It begins at 2; successful Task 1 decrements it to 1. Repair `r0` sets `h'=1`, and `r1` sets `h'=2`. A successful Task 2 at load `ell` requires `h>=ell` and then decrements health by one.

The exact functional contrasts are:

| Load | r0 (h=1) | r1 (h=2) | TV_func | TV_state_profile |
|---|---|---|---:|---:|
| ell=1 | SUCCESS, h_final=0 | SUCCESS, h_final=1 | 0 | 1 |
| ell=2 | APPARATUS_DEGRADED, h_final=1 | SUCCESS, h_final=1 | 1 | 1 |

R2 uses `TV_func(ell=2)=1` plus a valid causal `M_prod` read→repair-action trace. `TV_func(ell=1)=0` is the required functional null control. The full-state TV at load 1 is diagnostic only and cannot satisfy R2.

**Important unresolved design limitation:** with Task 1 changing `h:2→1`, `r0` setting `h'=1`, and ordinary Task 2 requiring only `h≥1`, the no-repair R0 arm also succeeds at `ell=1`. `r0` has zero health gain and consumes resources without improving the ordinary-load outcome. In the reference dose-3 run, no-repair R0 also retains enough energy to pass all three stress scenarios (`V_rob=1`), while R_int/r0 fails `omega_loss_E` (`V_rob=0`). Thus the current R1 comparator actually favours no repair on the declared load-1 robustness endpoint. The implementation therefore reports `R1_FUNCTIONAL_BENEFIT=NOT_DEMONSTRATED_FOR_r0_UNDER_D3_RULES`. This is not fixed by changing code. The design owner must either accept R1 as “repair instruction executed from inherited stock, with no demonstrated functional necessity/benefit” or change a preregistered health/load rule in a later specification delta. The code does not silently invent an extra wear event.

The v0.4.3 JSON manifest is the authoritative source for the resource vectors carried into v0.5.1: Task 1 and Task 2 each have cost `(1,0,0,0)` and byproduct `(0,0,1,0)` (one unit of W, not U); r0/r1 have cost `(1,1,0,0)` and the v0.5.1-identical byproduct `(0,0,1,0)`. The earlier prose representation that placed the task byproduct in U is inconsistent with the uploaded v0.4.3 manifest and is not used by this implementation. The old r1-specific `U+1` is explicitly removed per F13.

## 6. D5 resource arithmetic

The v0.4.3 manifest fixes the operation-cost basis used here: reads cost zero; Task 1 and Task 2 each consume one energy and create one waste; r0/r1 each consume one energy and one material and create one waste; r0/r1 byproducts are identical (the old r1 `U+1` difference is removed). Initial material is 2.

For `R_int` with fixed r0:

- nominal energy requirement = 1 (Task 1) + 1 (repair) + 1 (Task 2) = 3;
- robust requirement under `omega_loss_E` = 3 + 1 = 4;
- `omega_loss_M` is applied after repair, taking material 1→0, but Task 2 has no material cost;
- delay consumes one time unit but remains within `H_max=9`.

Exact enumeration over `E∈{1,2,3,4}` computes `E*_nominal=3` and `E*_robust=4`. Capacity is `(4,3,3,3)`. The code uses one component-wise capacity implementation; no second cap of 3 remains. The saturation control verifies inflow `(1,1,0,0)` from `(4,2,0,0)` leaves `(4,3,0,0)` and spills `(1,0,0,0)`.

## 7. D6 exact arithmetic

Probability laws accept only `int` or `Fraction`, reject booleans/floats/negative/non-normalized masses, and use exact fractions for TV. An independent direct-sum implementation checks the same support union. TV invariants include identity, symmetry, disjoint-support maximum and `[0,1]` bounds.

## 8. D7 H-Q status

The implementation provides a finite stage-qualified intervention alphabet and generator for sequences of up to two non-queued interventions. `continue` is a no-op stage progression, not a queued command. It provides exact deterministic partition-refinement utilities and unit controls. The complete intervention-to-transition adapter is still pending; the 96 A and 126 B-LITE schedules are generated, but they have not yet been exhausted against the full model state graph.

The observable contract separates `O_D`, `O_eval`, and diagnostic `J_trace`. The complete sequence generator emits an explicit `continue@stage_k` at each stage and forbids conflicting same-stage interventions on the same variable. The four intended reports remain separate: H-Q-task, H-Q-control, H-Q-R1, and H-Q-R2. However, the complete intervention-to-transition adapter for the v0.5.1 oracle/policy/repair kernel has not yet been independently validated. Consequently, the full four model partitions are **NOT EVALUATED**. H-Q must not be marked PASS from the generic algorithm control alone.

## 9. Release boundary

This package is a new finite reference implementation. It does not simulate producer C's production/transfer costs; those remain trusted prehistory. It does not implement X27-B-FULL recycling, resource reproduction, D2, new-record creation/R063, or X28. No software result establishes a physical mechanism. G0 reachable closure, full H-Q partitions, independent source review, DESIGN_FROZEN and G7 remain open.
