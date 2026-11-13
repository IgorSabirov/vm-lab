# X26 spectral branch A — R040 trimer + analytic 1D bath

**Design/package status:** executable conditional model.
**Scientific status:** not ADD-derived; no new result about NOW or the physical carrier.
**VM status:** package only; target-VM calibration and main submit are not performed.

## Question answered by this branch

For the already documented conditional R040 trimer, what is the exact projected spectral problem when node 2 is attached to a specified analytic continuum, and can we distinguish (a) a direct embedded eigenvalue, (b) a second-sheet resonance, and (c) a Fano line-shape zero without conflating them?

The bath law is an explicit imported assumption: an infinite homogeneous 1D nearest-neighbour chain with hopping `kappa`, onsite energy `bath_onsite`, and contact `g` to trimer node 2. It is not derived from the ADD topology, `K1`, or `K2`.

## Full operator and exact reduction

Use internal basis `(V,1,2)` and

\[
H_N=\begin{pmatrix}E_V&t_1&\gamma_d\\t_1&E_1&t_2\\\gamma_d&t_2&E_2\end{pmatrix}.
\]

The bath is the bi-infinite chain with dispersion

\[
E(k)=\epsilon_b+2\kappa\cos k,
\]

and the sole contact is `g (|2><0|+|0><2|)`. Its local Green function and self-energy are analytic:

\[
G_{00}(z)=\frac{1}{\sqrt{z-\epsilon_b-2\kappa}\sqrt{z-\epsilon_b+2\kappa}},\qquad s_b(z)=g^2G_{00}(z).
\]

The branch is fixed by `G_00(z)~1/z` at infinity. On the upper edge of the band, `Im s_b(E+i0)=-pi*j_b(E)` with the density implemented in `bath.py`.

Partition `P=(V,1)` and `Q=(2+bath)`. With `h=H_PP` and `v=(gamma_d,t2)^T`, the exact Feshbach operator is

\[
H_P(z)=h+\frac{vv^\dagger}{z-E_2-s_b(z)}.
\]

No constant 2x2 replacement is made. The determinant and projected-resolvent Schur identities are checked numerically. The absolutely continuous measure is `J_eff(E)`; Q-block bound states outside the bath band are kept as point masses and included in a matrix sum-rule check.

## Mechanism separation

- **Direct BIC:** tested from the full 3-mode eigen-equation, zero amplitude at the only open port, energy strictly inside the infinite-chain band, and vanishing continuum component.
- **Z2-protected subfamily:** separately tested under `E_V=E_1` and `gamma_d=t_2`, where exchange `V<->1` is an exact symmetry.
- **Parametric dark state:** the more general tuned R040 family need not possess that Z2 symmetry.
- **Second-sheet resonance:** root of the self-consistent determinant using the explicit adjacent-sheet continuation. The reported width is only `-2 Im z` for a converged lower-half-plane root.
- **Fano zero:** the helper is a line-shape control only. It never returns a BIC verdict and is not a full multi-port scattering calculation.

## Continuum and finite-N rules

The infinite-chain Green function is analytic and defines the continuum, so no polynomial spectral-density fit is needed. Finite periodic rings are used only to check off-axis resolvent convergence and moments. They are closed Hermitian systems: `Gamma_N_finite_ring` remains null. A local `delta_N(E)=1/[N rho(E)]` is reported as a level-resolution diagnostic. For a separately solved infinite-chain pole, `Gamma_infinity/delta_N` is a resolution ratio, not a finite-box width.

## Loading

For constant H, the dark spectral projector commutes with the full trimer+ring Hamiltonian, so zero initial dark weight remains zero. A generic time-dependent control API is included separately; its control Hamiltonian and envelope must be supplied explicitly. It calculates external work in model energy units but leaves actuator, reset, reservoir, and entropy costs `NOT_EVALUABLE` until those subsystems are specified. No loading operation is silently included in the spectral-only run.

## Inputs and VM gate

`configs/R040_SPECTRAL_INPUT.template.json` deliberately lacks physical model parameters and second-sheet seeds. A user must separately accept the conditional model assumptions. Provenance classes distinguish `ADD_DERIVED`, `MODEL_ASSUMPTION`, `EXTERNAL_CALIBRATION`, and `NOT_AVAILABLE`; a generic `VALIDATED` label is not accepted.

The VM main preflight also requires a frozen target-VM calibration/forecast with hashes, environment fingerprint, hard wall, memory and disk budgets. The default manifest is intentionally blocked. `run_vm.sh` executes in the environment where it is invoked; it does not submit a VM job. Use the repository's existing VM launch route and fixed Git commit only after its normal runtime gate is satisfied.

## Explicit non-claims

This package does not derive the three R040 modes, the R040 matrix elements, the bath hopping, the contact, or the actuator from ADD. It does not establish a global BIC on a growing ADD orbit. It does not update R040/R041/R042/R105/R115/L05/B09/X10 or the NOW result registers.
