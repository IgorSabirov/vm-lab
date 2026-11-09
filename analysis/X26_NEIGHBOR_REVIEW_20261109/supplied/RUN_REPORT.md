# X26 execution report

**Run date:** 2026-11-09  
**Scope:** X26-A toy spectral control + X26-B explicit ADD adapter blockers.  
**Scientific status:** the ADD–Fano/BIC bridge is **not established**.

## Execution

Command:

```bash
python -m unittest -v test_x26.py
python run_x26.py --out x26_report.json
```

Result: **7/7 unit tests passed**. The report was written to `x26_report.json`.

## X26-A findings (toy model only)

- T1: `PASS_ALGEBRAIC_SANITY_CHECK`. The selected model has one open continuum channel and two internal modes, so rank(W) <= 1 follows from matrix dimensions. This does not show that ADD produces a common continuum.
- T2: `PASS_TOY_MODEL`. Dark-vector eigen-residual: approximately `5.05e-17`.
- T3: `PASS_TOY_MODEL`. The dark state is embedded in the specified flat continuum band; because the form factor is factorized and `W(E)d=0` throughout the band, its continuum component vanishes and is normalizable.
- T4: `NOT_CLASSIFIED_NO_DECLARED_SYMMETRY`. Numerical log-log slopes:
  - internal detuning: approximately `2.0032`;
  - added which-path channel: approximately `2.0000`;
  - common-coupling rescale: width remains at floating-point zero.

  The two quadratic liftings occur in this deliberately tuned toy model. Therefore quadratic scaling is not evidence, by itself, of symmetry protection.
- T5: `PARTIAL_STATIC_NO_LOADING`. The exact dark state is decoupled from the same stationary continuum. A time-dependent loading protocol remains unimplemented.
- N1: `PASS_NEGATIVE_CONTROL`. Two independent open continua give rank(W)=2 and no nontrivial dark kernel.
- N2: mapping-specific only. The package includes a counterexample in which two resonances are assigned to the same ADD channel (`K1>0, K2=0`) and still form a toy BIC. Thus `K1>0 && K2>0` is not a general BIC condition.
- N3: `PASS_NEGATIVE_CONTROL`. The scalar Fano amplitude has a zero while the resonance width remains finite; the zero is not a BIC.
- N4: sector labels are compared, but no quantum superselection statement is made.
- N5: `BLOCKED_NOT_RUN`. Exact `carrier.py` source bytes and executable transport interface are absent from the supplied files.

## X26-B status

`BLOCKED_NO_PHYSICAL_ADD_SPECTRAL_INPUTS`.

Explicit missing inputs: exact verified carrier source; patch enumerator and K parser; quantum lift; physical identification of two resonant modes; ADD-derived internal Hamiltonian; physical environment and density of states; all-channel coupling matrix `W_mu,c(E)`; symmetry representation and perturbation classes; loading protocol.

The helper `validate_finite_closed_orbit_lift()` only validates a genuinely closed finite permutation orbit and its K commutators. It does not construct the full Hilbert space of the growing carrier or establish superselection.

## Verdict

```text
X26_A_CONTROL_MODEL_EXECUTED
X26_B_BLOCKED_NO_PHYSICAL_ADD_SPECTRAL_INPUTS
ADD_FANO_BIC_BRIDGE_NOT_ESTABLISHED
```

No claim is made about ADD source conformance, NOW integration, SSB, or closure of L07/L09/L10.
