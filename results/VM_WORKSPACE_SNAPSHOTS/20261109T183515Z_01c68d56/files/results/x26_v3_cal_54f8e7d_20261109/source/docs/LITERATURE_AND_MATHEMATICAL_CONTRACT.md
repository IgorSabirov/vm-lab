# X26 R040 + analytic bath: mathematical contract

## Status and scope

This package is a **conditional spectral model**, not a derivation from ADD and
not a result about the NOW law. It implements the inherited R040 three-mode
Hamiltonian (basis `V,1,2`) with the bath attached only to mode 2, plus an
explicit additional bath assumption: an infinite one-dimensional homogeneous
nearest-neighbour tight-binding chain. The values `E_V,E_1,E_2,t_1,t_2,gamma_d,
kappa,g` are not inferred from `K1,K2`.

## Full model

\[
H_N=\begin{pmatrix}E_V&t_1&\gamma_d\\t_1&E_1&t_2\\\gamma_d&t_2&E_2\end{pmatrix},\quad
H_b=\epsilon_b\sum_n|n\rangle\langle n|+
\kappa\sum_n(|n\rangle\langle n+1|+h.c.),
\]
with contact `g (|2><0| + h.c.)`. `hbar=1` in numerical integrations unless explicitly supplied.

## Analytic bath

\[
G_{00}^{I}(z)=\frac{1}{\sqrt{z-\epsilon_b-2\kappa}\sqrt{z-\epsilon_b+2\kappa}},
\quad s_b(z)=g^2G_{00}^{I}(z).
\]
The product branch is chosen so `G_00(z) ~ 1/z` at infinity. On the upper
rim of the band, `Im s_b(E+i0)=-pi*j_b(E)` with
\[
j_b(E)=\frac{g^2}{\pi\sqrt{4\kappa^2-(E-\epsilon_b)^2}}.
\]
On the adjacent second-sheet chart used for decaying poles, `G_II=-G_I` in the
lower-half-plane resonance region. A pole is accepted as a decaying resonance
only for `Im(z)<0`; a nonnegative imaginary part is rejected.

## Exact Feshbach reduction

Let `h=[[E_V,t_1],[t_1,E_1]]`, `v=(gamma_d,t_2)^T`, and
`q(z)=z-E_2-s_b(z)`. Then
\[
H_P(z)=h+\frac{vv^\dagger}{q(z)},\qquad
P(z-H)^{-1}P=[z-H_P(z)]^{-1}.
\]
The reduced continuous density is
\[
J_{eff}(E)=\frac{j_b(E)vv^\dagger}{|E-E_2-s_b(E+i0)|^2}.
\]
This is only the absolutely-continuous part. Real roots of `q(E)=0` outside
the band give point masses with residue
\[
R_b=\frac{vv^\dagger}{1-s_b'(E_b)}.
\]
Those atoms are computed separately; discarding them would make the reduced
spectral measure incomplete. The runner checks the matrix sum rule
`integral J_eff(E)dE + sum_b R_b = vv^dagger` numerically.

## BIC vs pole

For nonzero `t_2,gamma_d`, the inherited dark vector is
\[
|D\rangle=(t_2,-\gamma_d,0)^T/\sqrt{t_2^2+\gamma_d^2},\quad
E_D=E_1-t_1t_2/\gamma_d.
\]
It is an embedded eigenstate only if it is an eigenvector of the tuned
`H_N`, `E_D` is strictly inside the infinite-chain band, and its amplitude at
the only bath port is exactly zero. The continuum component then vanishes
identically, hence is normalisable. A finite ring is closed and is never called
a continuum BIC by this package.

Resonance poles are solved separately from
`det[z I - H_N - s_II(z)|2><2|]=0`. The pole solver reports `Gamma=-2 Im z`
only for a converged lower-half-plane second-sheet root. Pole width is not
substituted for the direct BIC conditions.

## Finite N limit

A periodic N-site ring is a quadrature/finite-volume approximation to the bath
measure. It is Hermitian at every finite N; therefore `Gamma_N_finite_ring`
is deliberately null. The package reports the mean band spacing `delta_N=4kappa/N`,
`Gamma_infinity/delta_N` only when an independently solved infinite-chain pole
width is supplied, and convergence of off-axis Green functions and low moments.
No finite-box irreversible width is manufactured.

## Loading is separate

For constant `H`, the spectral projector onto `D` commutes with `H`; zero
initial overlap remains zero. `loading.py` accepts an explicit `H_control` and
its envelope, integrates the time-dependent Schrödinger equation, and computes
external work `int <psi|dH/dt|psi> dt`. It does not invent an actuator, reset
cycle, reservoir, or entropy cost. Those costs remain `NOT_EVALUABLE` without
additional physical/model inputs.

## References

- H. Feshbach, *Unified theory of nuclear reactions*, Annals of Physics 5 (1958),
  357–390, DOI: 10.1016/0003-4916(58)90007-1.
- H. Feshbach, *A unified theory of nuclear reactions II*, Annals of Physics 19
  (1962), 287–313, DOI: 10.1016/0003-4916(62)90221-X.
- H. Friedrich and D. Wintgen, *Interfering resonances and bound states in the
  continuum*, Phys. Rev. A 32 (1985), 3231, DOI: 10.1103/PhysRevA.32.3231.
- U. Fano, *Effects of Configuration Interaction on Intensities and Phase Shifts*,
  Phys. Rev. 124 (1961), 1866, DOI: 10.1103/PhysRev.124.1866. The small `fano.py`
  helper implements only the normalized line shape, not a multi-port scattering model.
- C. W. Hsu et al., *Bound states in the continuum*, Nature Reviews Materials 1,
  16048 (2016), DOI: 10.1038/natrevmats.2016.48.
- The one-dimensional tight-binding local Green function is derived directly
  from the nearest-neighbour resolvent recurrence in `bath.py` and checked against
  the finite-ring resolvent sequence; no separate empirical fit is used.
- F. Verstraete, M. M. Wolf and J. I. Cirac, *Quantum computation and quantum-state
  engineering driven by dissipation*, Nature Physics 5, 633–636 (2009),
  DOI: 10.1038/nphys1342. Used only as a general loading-method reference.
