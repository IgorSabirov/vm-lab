# Validation record — X27 v0.4.2 reference kernel

**Validation type:** software/unit/control validation only  
**Scientific main run:** NOT EXECUTED  
**Design freeze:** NOT FROZEN

Reproduction:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m x27.cli smoke --output validation/smoke_report.json
```

Observed local result:

```text
Ran 22 tests
OK
```

Exact diagnostic report generated at `validation/smoke_report.json`:

- G0 X27-A: 132 reachable physical states, limit 350,000 — PASS.
- G0 X27-B-LITE: 6,752 reachable physical states, limit 350,000 — PASS. Contexts include R0/R_ext/R_int crossed with ω0/delay/loss_E/loss_M. The exact sorted-state-hash closure digest is recorded; the large raw hash list is not embedded.
- H-Q X27-A: 11 predictive classes over 128 decision nodes; 64 terminal output nodes represented by 3 distinct terminal signatures.
- H-Q X27-B-LITE: 79 predictive classes over 832 decision nodes; 288 terminal output nodes represented by 15 distinct terminal signatures; `(V_nom,V_rob)` included as a pre-execution output.
- H-Q domain rule: operational helper stages remain in the transition refinement, published equivalence classes are restricted to `σ∈{1,2,5,6}`, and terminal states are outcome leaves rather than partition members.
- Apparatus class contrast: `TV(A1,A0)=1`, `TV(A2,A0)=1`, `TV(A1,A2)=0`; trace-use events agree with the A1/A2-versus-A0 functional comparison.
- Resource event ledger records before/inflow/cost/byproduct/after/spill/exhaustion for each operation; losses carry explicit before/after and applicability fields.
- E2: 6/6 passed.
- Positive controls: 9/9 passed.
- Negative controls: 12/12 passed, including side-channel leak, order-dependence and complete stress-scenario enumeration.

Pre-registered reference-model expectation recovered:

```text
R_int / fixed r0:
  Task 2 = SUCCESS
  V_nom = 1
  V_rob = 0
  R_final = (0, 1, 3, 0)

R_int / causal M_prod=r0 versus r1:
  both Task 2 = SUCCESS
  Delta U = 1
  exact joint-profile TV = 1
```

This is a statement about the software model just validated. It is not a physical-mechanism result and does not itself close the experimental preregistration. The generated JSON is the machine-readable record for this validation.

The earlier H-Q counts from a partition that also contained terminal states are superseded. The current report follows the stated domain exactly: terminal outcomes are leaves, and only states in the decision region are included in the published equivalence classes.
