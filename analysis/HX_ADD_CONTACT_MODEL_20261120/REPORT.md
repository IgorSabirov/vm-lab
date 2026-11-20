# First effective ADD contact Hamiltonian: thermodynamics and kinetic test

20 November 2026. This is the first explicit effective \(H_X\) built from the latest contact-balance result. It is a controlled toy Hamiltonian with an open kinetic completion, not yet a microscopic derivation of physical X.

## 1. Inputs carried forward from main

The latest contact-balance classification gives:

- Under passive \(Q\) and a context-independent \(12\leftrightarrow3\) gap, all cyclic four-site potentials reduce to \(E=hL+A N_a+B N_b\). This class has zero contrast on all five matched 24-site witnesses.
- Order sensitivity survives when the contact price depends on its local neighborhood. The simplest retained example is \(E_4=\sum_i a_i a_{i+1}a_{i+2}a_{i+3}\), invariant under passive \(Q\).
- The ADD paper's Theorem 5 is a conserved **bit count**. It does not assign a dimensional energy in joules or MeV to a radiation bit. The parameter \(h\) below is the proposed physical energy per contact/radiation quantum, inherited from the contact-balance ansatz; its dimensional value remains open.

## 2. Effective Hamiltonian

At fixed ring length \(L\), let \(a_i,b_i\in\{0,1\}\) be the matter-channel port bits and \(r_i^L,r_i^R\in\{0,1\}\) the two radiation-channel port bits. Define

\[
N_4(a)=\sum_{i=0}^{L-1}a_i a_{i+1}a_{i+2}a_{i+3}
\]

with cyclic indices. The minimal effective Hamiltonian is

\[
\boxed{H_X=hL+J N_4(a)+hN_\gamma,\qquad
N_\gamma=\sum_i(r_i^L+r_i^R).}
\]

The \(b_i\) bits are retained as a \(2^L\) zero-energy degeneracy in this first version. \(J\) is the neighbor-sensitive contact-order coupling. \(h\) is the base energy per graph vertex/contact and the proposed energy quantum of a radiation bit. The ratio \(J/h\) is not derived by ADD; the scan keeps it explicit.

For one merge \(12\to3\), \(\Delta L=-1\), so

\[
\Delta H_{\rm graph}=-h+J\Delta N_4,
\qquad E_{\rm release}=h-J\Delta N_4.
\]

The reservoir must gain the opposite energy. This is the energy-ledger completion; a port-by-port radiation update is still to be derived.

### Exact event-context check

Enumerating cyclic C1 words of lengths 3–8 with no pre-existing 3 and exactly one 12 redex gives:

| \(\Delta N_4\) | Number of contexts | Released energy for \(J=h\) |
|---:|---:|---:|
| 0 | 4155 | \(+h\) |
| 1 | 242 | \(0\) |
| 2 | 65 | \(-h\) |
| 3 | 38 | \(-2h\) |

Thus a fixed one-bit emission of \(+h\) per merge is **not** compatible with this neighbor-sensitive term in every context. Depending on the surrounding word, the radiation sector must also absorb one or two quanta. This is why the article's conserved bit count alone is not a dimensional energy law.

## 3. Canonical ensemble and exact partition function

Choose a canonical ensemble at fixed \(L\), with \(k_B=1\). The matter \(b\)-bits contribute \(2^L\); the two radiation port bits per vertex contribute \((1+e^{-\beta h})^{2L}\). The four-site matter term is counted exactly by an eight-state transfer matrix (equivalently, the exact DP over the distribution of \(N_4\)):

\[
Z_a(L,\beta J)=\sum_{a\in\{0,1\}^L}e^{-\beta JN_4(a)}
=\operatorname{Tr}T(\beta J)^L.
\]

Therefore

\[
\boxed{Z_L=e^{-\beta hL}\,2^L\,Z_a(L,\beta J)
(1+e^{-\beta h})^{2L}.}
\]

The thermodynamic quantities follow without numerical differentiation:

\[
F=-T\ln Z_L,\quad S=\ln Z_L+\beta\langle H_X\rangle,
\]

\[
\frac{C_{L}}{k_B}=\beta^2
\left[J^2\operatorname{Var}(N_4)+
2Lh^2 f_\gamma(1-f_\gamma)\right],
\qquad f_\gamma=(e^{\beta h}+1)^{-1}.
\]

\(C_L\) is at fixed graph length. Calling it the BH1 \(C_R\) requires a physical map \(L\mapsto R\), which does not yet exist.

### Numerical benchmark

For \(L=24\), \(J/h=1\):

| \(h/T_X\) | \(F/T_X\) | \(S/k_B\) | \(C_L/k_B\) | \(\langle N_4\rangle\) |
|---:|---:|---:|---:|---:|
| 0.25 | -54.62709 | 66.10212 | 0.84543 | 0.88457 |
| 0.50 | -43.56055 | 64.90361 | 3.05671 | 0.56418 |
| 1.00 | -23.64577 | 60.82045 | 9.80163 | 0.26550 |
| 2.00 | 9.44832 | 50.15125 | 20.50983 | 0.07804 |

The exact state-count check is \(2^{24}=16,777,216\). The table is dimensionless; no MeV scale has been inserted.

## 4. Kinetic completion and relaxation time

A first open-system kinetic law is the single-site heat-bath generator on the \(a_i\) bits:

\[
(\mathcal L_X f)(a)=\sum_i
\frac{\Gamma_0}{1+e^{\beta\Delta_iH_X}}
\big[f(a^{(i)})-f(a)\big].
\]

It obeys detailed balance for the canonical distribution. Diagonalizing the finite generator for \(L=8\) gives:

| \(\beta J\) | Spectral gap / \(\Gamma_0\) | \(\tau_X\Gamma_0\) |
|---:|---:|---:|
| 0.25 | 0.936927 | 1.067319 |
| 0.50 | 0.878358 | 1.138489 |
| 1.00 | 0.790029 | 1.265776 |
| 2.00 | 0.699861 | 1.428855 |

At the BBN comparison point \(h/T_X=0.5,\ J/h=1\), \(\beta J=0.5\), hence

\[
\tau_X=\frac{1.13849}{\Gamma_0}.
\]

The condition \(\tau_X\le H^{-1}\) becomes

\[
\boxed{\Gamma_0/H\ge1.13849.}
\]

This is a **conditional threshold**, not a measured result: \(\Gamma_0\) is an arbitrary attempt rate in the chosen Glauber completion. This generator is not the deterministic reversible ADD map \(F=QI\). A microscopic coupling to the radiation port bits must replace it before claiming an ADD-derived relaxation time.

## 5. BBN budget check

The latest contact-balance file fixes

\[
\chi\nu g\xi^4=0.0445180754118,
\qquad g=h/T_X,\quad \xi=T_X/T_\gamma.
\]

At \(\xi=0.5\),

\[
\chi\nu g=0.7122892066.
\]

If the benchmark \(g=0.5\) is selected, this requires

\[
\chi\nu=1.4245784132.
\]

The Hamiltonian computes an equilibrium radiation-bit occupation fraction \(f_\gamma\), but that is **not** the event density \(\nu=(M-S)/(VT_X^3)\). This model does not yet determine the physical volume, event rate/density, transfer efficiency \(\chi\), or \(h/T_X\). Consequently it cannot yet claim to supply the BBN energy budget without fitting. It reproduces the required parameter combination, not its microscopic value.

## 6. Status and next physical closure

- Effective static \(H_X\): **constructed**.
- \(Z,F,S,C_L\) at fixed \(L\): **computed exactly** for the stated ensemble.
- Finite-size thermal relaxation: **computed for an explicitly chosen Glauber process**.
- \(\tau_X/H^{-1}\): **not identified**, because \(\Gamma_0/H\) is unknown.
- Exact local event energy ledger: **computed**; a fixed \(+h\) emission per merge fails in some environments.
- BBN source sufficiency: **not yet established**; \(\chi,\nu,g\) remain independent physical inputs.
- Physical \(C_R\): **not yet available**, pending \(L\mapsto R\).

The next task is no longer to invent more static potentials. It is to derive the port-level radiation update and the microscopic transition generator from the ADD \(I,Q\) rules, including the energy changes \(h-J\Delta N_4\), then identify \(h\), \(J\), \(\Gamma_0\), and the physical volume. Only that closes the route from this effective Hamiltonian to BH1 and BBN.
