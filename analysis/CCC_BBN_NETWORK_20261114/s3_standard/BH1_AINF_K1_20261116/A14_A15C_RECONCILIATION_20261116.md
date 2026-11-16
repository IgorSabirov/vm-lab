# A∞ A14/A15c reconciliation — superseding erratum to the preliminary k=2 audit

**Date:** 2026-11-16  
**Status:** RESEARCH-SESSION CHECKS REPORTED / SOURCE MATCH FOR k=2,3,4 / FULL THERMAL RUN NOT REPOSITORY-REPRODUCED  
**Supersedes:** the preliminary verdict in `A_INFINITY_SPECTRAL_AUDIT_20261116.md` that treated all signed RS subtraction as a likely implementation defect. That earlier document is retained as historical audit trail; this addendum is the current disposition.

## 1. Definitive resolution of S1 vs S2 vs BAD

The two reports did conflict because they used different character bookkeeping. The conflict is resolved:

- **S1:** retain positive Racah–Speiser primaries and use shortened character numerators for conserved multiplets. Correct.
- **S2:** retain signed Racah–Speiser coefficients and use long character numerators. Correct.
- **BAD:** retain signed Racah–Speiser coefficients and also use shortened numerators. Incorrect: the same null descendants are subtracted twice.

For a conformal primary with `Delta=j1+j2+2`, the long descendant numerator is `(2j1+1)(2j2+1)`; the shortened numerator is

`(2j1+1)(2j2+1) - 4*j1*j2*q`.

For the four conserved sectors in the k=2 graviton multiplet the short numerators are:

- SU(4) adjoint current, (j1,j2)=(1/2,1/2): `4-q`;
- supercurrent 4, (1,1/2): `6-2q`;
- conjugate supercurrent 4bar, (1/2,1): `6-2q`;
- stress tensor, (1,1): `9-4q`.

The four null submodules have dimensions 15, 8, 8 and 4, respectively:

`15+8+8+4=35`, hence `291-35=256`.

The negative RS entries encode those null submodules. They are not negative physical particle degeneracies. They may be represented either as signed RS terms with long characters (S2), or as omitted null terms plus short characters (S1). Do not combine both operations.

A research-session coefficient-by-coefficient character comparison reports `S1 == S2` and `S1 != BAD`. This is the correct resolution of the previous 291/256 dispute. The earlier blanket label "positive-only k=2 thermal sum invalid" is superseded: positive-only RS plus the correct short numerator is not the BAD implementation.

## 2. Meaning of 291 and 256

291 is the sum of the positive formal conformal-primary contributions before quotienting by the four null descendant modules. 256 is the physical shortened k=2 massless IIB graviton multiplet content (128 bosonic + 128 fermionic states). The 35-state difference is exactly the null/gauge content listed above.

This does not mean the bulk gas contains 291 states. The physical k=2 character is 256 states after shortening.

## 3. A14 source-level result

The research-session A14 checker reports component-by-component agreement of the reconstructed positive-primary list with the unorbifolded S5 spectrum table for k=2,3,4:

| k | Reconstructed positive entries | Source-table entries | Match | Signed null leftovers |
|---:|---:|---:|---|---:|
| 2 | 14 | 14 | exact | 4 |
| 3 | 25 | 25 | exact | 0 |
| 4 | 34 | 34 | exact | 0 |

Compared fields: conformal energy Delta, both Lorentz spins (j1,j2), SU(4) Dynkin labels and multiplicity. The source is the S5 spectrum presented before the Z3 projection in Ardehali–Liu–Szepietowski; the paper's orbifold projection must not be applied to this comparison. KRN remains the primary mass-spectrum reference.

**Current A14 status: `SOURCE_MATCHED_K2_K3_K4`.** This closes the low-level source-match test that was intended to catch a wrong k=2 thermal character. It does not prove every level of the infinite tower independently.

## 4. k=1 doubleton: boundary vs bulk

The k=1/p=1 representation is the boundary singleton/doubleton with 8 bosonic plus 8 fermionic states (16 total). It is not a propagating bulk KK supergravity multiplet. The bulk thermal gas correctly starts at k=2 after quotienting the doubleton.

Therefore an algorithm returning zero at k=1 is correct **for the bulk thermal catalogue**, but it must expose a separate boundary-singleton diagnostic returning 16. Do not change the bulk algorithm to insert 16 states into the thermal gas. Add two explicit tests:
- boundary/pre-quotient p=1 singleton dimension = 16;
- bulk/post-quotient p=1 contribution = 0 and first bulk level p=2.

## 5. Thermal values and provenance

The following values are research-session/peer-reported machine outputs, not a fresh repository CI run:

- S1 baseline at chi_HP: `ln Z_gas = 2.63032131`.
- BAD double-subtraction diagnostic: `ln Z_gas = 2.62211017`.
- Their difference is `0.00821114`, matching the extra null-module subtraction in BAD.

The value 2.62211017 is rejected as double subtraction. The S1 value 2.63032131 is the current peer baseline supported by the source-matched k=2,3,4 character prescription. It is still **not a repository-reproduced accepted result** until the complete runner, source tables, environment and output hashes are committed and a clean rerun is recorded. Report it as `ln Z_gas(chi_HP) ~= 2.63`, not twelve significant digits.

The earlier claim that 291 physical k=2 states were used was a category error: 291 counts formal positive RS primary terms before shortening; the thermal character with S1 correctly removes the 35 null descendants through the short numerators.

## 6. A15c: high-energy asymptotic test

A research-session run reports `k_max=150`, `epsilon_max=120`. Reported convergence:

| epsilon | level density / Weyl target | cumulative count / Weyl target |
|---:|---:|---:|
| 40 | 1.01759 | 1.08084 |
| 60 | 1.00779 | 1.04824 |
| 80 | 1.00438 | 1.03412 |
| 100 | 1.00280 | 1.02632 |
| 120 | 1.00195 | 1.02139 |

Thus local level-density deviation at epsilon=120 is 0.195%; cumulative-count deviation is 2.139%. A15c may be called `NUMERIC_CONVERGENCE_CONFIRMED_AT_EPS120` for the local-density criterion with a predeclared 0.5% tolerance. It does **not** pass a 1% cumulative-count criterion. The tolerance and observable must always be named; do not use a generic unconditional PASS.

The reported full thermal tail above k=46 at chi_HP is about 6.45e-37 relative, negligible for lnZ at HP. This is a thermal-tail statement and must not be confused with the high-energy Weyl test. The two cutoffs answer different questions.

The A15c scripts and output tables were reported as run in the research session, but are not yet present as committed repository artifacts. Their provenance remains research-session reported until added and cleanly rerun.

## 7. Error budget and precision policy

Pre-A14 estimates of a possible 10% k=2 character error and a ~6.4% effect on lnZ were risk budgets, not residual uncertainties after the source match. The S1/BAD 0.31% difference is no longer an uncertainty: BAD is a rejected double-subtraction scheme.

Current dominant reproducibility gap is not a known 6% physical uncertainty. It is the missing committed runner/output provenance and remaining higher-level/tail audit. Use `lnZ ~= 2.63` until the full run is committed; do not print spurious precision.

## 8. Revised priorities

1. Commit the reproducible source checker, S1/S2/BAD character runner, A15c runner, source-table transcription and machine outputs with hashes.
2. Add the explicit k=1 boundary-singleton vs bulk-quotient tests.
3. Freeze the A∞ baseline at `lnZ(chi_HP) ~= 2.63` pending clean repository rerun; do not reopen S1/BAD absent a new source-level counterexample.
4. In parallel, formulate one falsifiable X/portal candidate. It may be a deliberately provisional ansatz, clearly labelled as such, to make the cosmological equations testable.
5. Keep complete BBH one-loop determinants and finite-lambda corrections as precision work, not as prerequisites for beginning the X/portal branch.

## 9. Acceptance summary

- S1 vs S2: equivalent character bookkeeping.
- BAD: rejected double subtraction.
- k=2 physical content: 256; 291 is pre-shortening formal positive-primary count.
- A14: source matched for k=2,3,4 in the research-session checker.
- k=1: 16 boundary singleton states; zero contribution to bulk thermal KK gas.
- A15c: reported convergence at epsilon=120; local density 0.195% from Weyl target; cumulative count 2.139%.
- `lnZ(chi_HP) ~= 2.63`: peer/research-session baseline, not yet repository-reproduced.
- No BH1/BBN production calculation.
