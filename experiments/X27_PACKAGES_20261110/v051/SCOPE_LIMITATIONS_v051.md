# X27 v0.5.1 — limitations and unresolved scientific-design issues

**Status:** DRAFT / NOT FROZEN / MAIN RUN NOT EXECUTED.

This file records limitations that must remain visible in any report or repository presentation.

## 1. Oracle challenge is deliberately narrow

There are two evaluator contexts with identical public input and opposite binary target values. This is sufficient to make the evaluator target unavailable from public input alone and to compare the declared memory/payload policies under a small exhaustive capability matrix. It is not a representative task benchmark, and it cannot support a selector or generalization claim. `pi_fixed` and `pi_input` both emit zero because the public hint is constant zero; their equal score is a property of this narrow challenge, not evidence that the policies are generally equivalent.

## 2. Readout and score are separate

A policy can correctly read and faithfully transfer a source value yet produce an oracle-incorrect action when the source content is misaligned with the task case. Mechanical execution success is also independent from oracle correctness. Do not collapse `readout_fidelity`, `Y_action`, `Y_correct`, and `Y_status` into one success flag.

## 3. R1 does not currently demonstrate a functional repair benefit

After Task 1, apparatus health is 1. The fixed R1 repair protocol `r0` sets health to 1 again, so its health gain is zero. Task 2 at ordinary load 1 can already execute without repair. Paying the repair energy cost can reduce robust resource readiness compared with R0. The smoke output intentionally reports:

`R1_FUNCTIONAL_BENEFIT=NOT_DEMONSTRATED_FOR_r0_UNDER_D3_RULES`.

This is a genuine design limitation, not a reason to weaken the PASS criterion. Before freeze, the owner must decide whether to (a) retain this negative result, (b) define a predeclared wear/repair task in which r0 restores an actually lost capability, or (c) narrow the claim to the R2 high-load distinction. The existing R1 PASS must not be advertised as functional restoration.

## 4. R2 is a model-internal high-load contrast

The implementation predicts `TV_func(ell=1)=0` and `TV_func(ell=2)=1` with a causal `M_prod` read→repair-action trace. The health levels, repair map and load rule are model assumptions. This is not evidence that real repair processes behave this way. `TV_state_profile(ell=1)=1` arises from the stipulated final-health decrement and is diagnostic only, not the R2 criterion.

## 5. Dose thresholds are exact arithmetic under declared costs

The exact sweep computes nominal threshold 3 and robust threshold 4 under the current zero-cost reads, one-energy Task 1/Task 2 costs, one-energy/one-material repair and component capacity `(4,3,3,3)`. These values change if any operation cost, byproduct, disturbance timing, or readiness semantics change. They are not universal physical thresholds.

## 6. Capability controls are not a security sandbox

The AST/import audit and runtime whitelist detect accidental and ordinary unauthorized field access in the declared Python path. Arbitrary hostile Python code can introspect or exploit its runtime. Untrusted policies require process/OS isolation. NC15's exact 100/200 result is a deterministic balanced-label and ID-blindness diagnostic, not a confidence interval or a general statistical estimate.

## 7. H-Q and G0 remain uncomputed for the complete model

The finite intervention sequence families are generated and the generic partition-refinement algorithm is unit-tested. The v0.5.1-specific transition adapter and separate H-Q-task/control/R1/R2 partitions are not implemented/independently validated. Exact G0 closure for the complete v0.5.1 intervention kernel is also not reported. The historical v0.4.2 H-Q class counts do not transfer.

## 8. Other explicit exclusions

- H-MA is not evaluated in this v0.5.1 capability matrix because apparatus is held at A1; the separate A0/A1/A2 class contrast does not constitute an M×A factorial design.
- H-A-token remains `NOT_CLAIMED`; the baseline does not make instance identity a dynamic transition variable.
- C production and transfer remain trusted exogenous prehistory; the producer process is not simulated.
- B-FULL recycling/resource reproduction, D2 repeated readiness, new-record generation/R063, and X28 remain out of scope.
- No physical system, laboratory apparatus, biological system or independent external oracle was tested.

The software smoke can pass while these hypotheses remain untested or unsupported. `G7_MAIN_RUN` remains unauthorized until full specification freeze and independent audit.
