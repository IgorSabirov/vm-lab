# BH1 free thermal branch A — frozen computational contract

**ID:** BH1_FREE_BRANCH_A_20261116  
**Status:** FROZEN_SPECIFICATION_NOT_EXECUTED  
**Parent:** analysis/CCC_BBN_NETWORK_20261114/s3_standard/bh_bridge_20261115/REPORT.md at main commit cadf7235a64ffb893c26dab9adb689acf44ef915  
**Purpose:** compute the free, confined, large-N thermal branch A and its first two susceptibility derivatives without selecting a cosmological embedding, a portal, a nucleation law, or an interacting coupling regime.

## 1. Scientific question

Does the source-defined free branch A provide a finite, independently reproducible C_A(chi) and C_A'(chi) on a declared interval below its Hagedorn pole, and therefore make the A-side contribution to the constant-G level-line equation quantitatively testable?

This is not a BH1 physical realization, not a computation of branch B, and not a prediction of a cosmological transition.

## 2. Frozen theory and conventions

- Theory: four-dimensional free N=4 SYM on S^3_R x S^1_beta, zero gauge coupling, no chemical potentials, adjoint matter.
- Gauge group: compute both U(N) and SU(N) at leading large N. Do not silently substitute one for the other.
- Field content: n_S=6 real scalars, n_V=1 vector, n_F=4 Weyl fermions.
- Units: hbar=c=k_B=1; spatial volume V=2 pi^2 R^3.
- Dimensionless temperature: chi=TR; x=exp(-1/chi).
- Thermal/vacuum convention: normalized Haar measure and Aharony et al. confined-saddle normalization Z(chi->0)=1. This is the thermal contribution with the vacuum/Casimir term subtracted, not the absolute gravitational energy. No arbitrary additive constant may be introduced.
- Branch: uniform-holonomy confined saddle, leading large-N Gaussian result. Finite-N corrections and the deconfined saddle are out of scope.

## 3. Source-defined single-particle functions

For one real scalar, one vector, and one Weyl fermion on the unit three-sphere, use

z_S(y) = (y+y^2)/(1-y)^3
z_V(y) = (6y^2-2y^3)/(1-y)^3
z_F^(1)(y) = 4 y^(3/2)/(1-y)^3

Thus for N=4 SYM,

z_B(y)=6 z_S(y)+z_V(y)
z_F(y)=4 z_F^(1)(y)

z_n(chi)=z_B(exp(-n/chi))+(-1)^(n+1) z_F(exp(-n/chi)).

The fermionic alternating sign is part of the thermal trace and must not be dropped or replaced by an unsigned sum.

## 4. Confined partition functions

With I_A=-ln Z_A, define the leading large-N thermal actions

I_A,U^th(chi) = sum[n>=1] ln(1-z_n(chi))
I_A,SU^th(chi) = I_A,U^th(chi) + sum[n>=1] z_n(chi)/n.

The SU(N) correction follows from replacing each adjoint character tr(U^n) tr(U^(-n)) by tr(U^n) tr(U^(-n))-1. It is not an optional numerical correction.

These formulae are valid only on the confined side where every denominator is positive and the uniform saddle is locally stable. The first Hagedorn boundary is determined by the smallest positive root

z_1(chi_H)=1.

Do not evaluate the confined Gaussian expression at or above chi_H.

## 5. Thermodynamic observables

For either group, let I_A denote the corresponding action above. Define

C_A(chi)=-(chi^2/(2 pi^2)) I_A'(chi)
C_A'(chi)=d C_A/d chi.

This is the dimensionless heat-capacity density convention used by the parent bridge, with C_V,A=2 pi^2 C_A'(chi). Preserve this naming exactly; do not relabel C_A as the ordinary total heat capacity.

For auditability, compute each observable by two routes:

1. Action-derivative route: differentiate the convergent series for I_A, then evaluate C_A and C_A'.
2. Energy route: form E_A=(I_A-chi I_A')/R from the same action and differentiate with respect to T at fixed R; convert to the parent convention and compare.

The two routes must agree within the declared numerical error. A centered finite difference is a diagnostic only, not the primary derivative definition.

## 6. Derivative identities to implement

Let y_n=exp(-n/chi). Then

dy_n/dchi=(n/chi^2)y_n
z_n'=(n y_n/chi^2)[z_B'(y_n)+(-1)^(n+1)z_F'(y_n)].

For U(N),

I_A,U'=-sum[n>=1] z_n'/(1-z_n)
I_A,U''=-sum[n>=1] [z_n''/(1-z_n)+(z_n')^2/(1-z_n)^2].

For SU(N),

I_A,SU'=I_A,U'+sum[n>=1] z_n'/n
I_A,SU''=I_A,U''+sum[n>=1] z_n''/n.

And

C_A'=-(1/(2 pi^2))[2 chi I_A'+chi^2 I_A''].

All derivatives in these expressions are with respect to chi, unless the argument explicitly says y.

## 7. Domain and numerical protocol

1. Locate chi_H by a bracketed root solve of z_1(chi)-1=0; independently verify the residual and monotonicity on the bracket.
2. Define the computational domain as 0<chi<=chi_H-delta_H. The numerical value of delta_H is an output of a declared resolution study, not a fitted parameter.
3. Use a sequence of truncations n_max and report convergence of I_A,I_A',I_A'',C_A,C_A'. Bound the omitted tail using an explicit analytic/geometric bound valid on the chosen interval; if no defensible bound is established, mark the tail as empirically converged only.
4. Resolve the near-pole region separately. Do not extrapolate through the pole and do not identify the free Hagedorn pole with the interacting HP spinodal or the O(lambda^2) metastability window.
5. Report U(N) and SU(N) separately, including the size and sign of their difference.
6. Record precision, arithmetic backend, root tolerance, summation cutoff, derivative method, wall time, and all residuals. A plot without machine-readable tables is insufficient.

## 8. Required tests

- T01 source functions: reproduce the three single-particle functions and the N=4 multiplicities.
- T02 fermion parity: verify the alternating (-1)^(n+1) factor term by term.
- T03 group subtraction: verify I_SU-I_U=sum z_n/n numerically and symbolically at truncated order.
- T04 low-temperature limit: verify I_A,C_A,C_A' -> 0 as chi -> 0+.
- T05 Hagedorn root: verify z_1(chi_H)=1 to the declared tolerance and reject evaluation at/above the root.
- T06 convergence: demonstrate cutoff convergence for every reported observable, not only for I_A.
- T07 derivative cross-check: action-derivative and energy routes agree within combined error.
- T08 finite-difference diagnostic: derivative estimates converge under step refinement away from the pole; failure here blocks derivative acceptance.
- T09 positivity/stability: flag any interval where the confined Gaussian factors cease to be positive; no silent clipping.
- T10 reproducibility: a clean rerun regenerates identical metadata and agrees within declared tolerances.

## 9. Outputs

- SPEC.json: frozen theory, conventions, domain rules, tolerances and status.
- RESULT.json: chi_H, domain, group-specific observables, convergence table, derivative cross-checks and residuals.
- DATA.csv: sampled chi,I_A,I_A',I_A'',C_A,C_A' for both groups.
- CHECKS.json: individual test outcomes; any failure remains visible.
- REPORT.md: derivation, numerical method, domain limitations, and interpretation boundary.

## 10. Acceptance gate

Scientific status may become FREE_BRANCH_A_NUMERICALLY_REPRODUCED only if T01-T10 pass, both groups are reported, the tail/domain limitation is explicit, and the two derivative routes agree. Otherwise status is REVIEW or FAIL, with no selective omission of failed tests.

Even a full pass establishes only the free confined branch A in the declared large-N, zero-coupling approximation. It does not determine the interacting branch B, Delta C(chi), N, lambda, the absolute vacuum energy, f, R-embedding, transition trigger, kinetic law, collision terms, or cosmological perturbations. In particular it does not authorize BH1/BBN execution or scientific acceptance.

## 11. Primary source and source boundary

Aharony, Marsano, Minwalla, Papadodimas & Van Raamsdonk, The Hagedorn/Deconfinement Phase Transition in Weakly Coupled Large N Gauge Theories, hep-th/0310285, section 3.5 equations (3.19)-(3.20), section 5.2 equation (5.10), and discussion of the SU(N) adjoint-character subtraction. The paper explicitly fixes the vacuum normalization by Z(x=0)=1 for the confined Gaussian result and notes the separate Casimir-energy convention.

- arXiv: https://arxiv.org/abs/hep-th/0310285
- PDF: https://arxiv.org/pdf/hep-th/0310285

The source is a free/weak-coupling large-N thermal calculation. It is used here only for branch A. It is not evidence that the strongly coupled Hawking-Page branch B is described by the same functions.
