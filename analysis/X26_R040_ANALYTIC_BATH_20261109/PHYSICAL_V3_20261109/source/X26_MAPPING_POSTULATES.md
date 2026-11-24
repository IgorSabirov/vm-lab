# X26_MAPPING_POSTULATES — branch B/C interface contract

**Status:** `DESIGN_CANDIDATE / MODEL_ASSUMPTION / NOT_ACCEPTED_BY_DEFAULT`  
**Purpose:** specify executable, falsifiable interfaces for ADD → R040 parameters (`Phi`), ADD transition → loading mechanism (`Psi`), and transport of a protected projector. This document does not assert that any of these laws follows from ADD.

## 1. Epistemic boundary

The pinned carrier source is `experiments/now_integrated_v1/nowexp/carrier.py`, Git blob SHA-1:

`6e44c12cd1f27aadc9e2c73c1f82222944cd2e7b`

Its operational word has four bits per vertex in the order `(a1,b1,a2,b2)`. For a word `X=(s_i)` the code recomputes

\[
 n_{a1}=\sum_i(s_i)_0,\quad n_{b1}=\sum_i(s_i)_1,\quad
 n_{a2}=\sum_i(s_i)_2,\quad n_{b2}=\sum_i(s_i)_3,
\]
\[
 K_1=n_{a1}n_{b1},\qquad K_2=n_{a2}n_{b2}.
\]

These remain combinatorial labels. They are not complex amplitudes, energies, or quantum superselection charges. The exporter verifies the exact carrier Git blob before importing `full_step`; it does not invent a finite permutation for an active growing orbit.

The three R040 roles `V`, `1`, and `2` are selectors into a particular carrier snapshot. Their identification is itself an explicit model input. Two particle species are not automatically two resonant modes.

## 2. Candidate Phi: local density and local barrier law

For an ADD word snapshot and a fixed radius `r`, define an ordered cyclic neighbourhood

\[
N_r(i)=(s_{i-r},\ldots,s_i,\ldots,s_{i+r}),
\]

and the local total occupancy

\[
q_i(X)=\frac{1}{4(2r+1)}\sum_{j\in N_r(i)}\operatorname{popcount}(s_j).
\]

The order is retained when constructing the feature record; the scalar `q_i` is only one declared feature. No global `K` enters `Phi`.

One deliberately minimal postulate is

\[
E_V(X)=E_{p}^{(0)}+\lambda_p q_V(X),\qquad
E_1(X)=E_{p}^{(0)}+\lambda_p q_1(X),
\]
\[
E_2(X)=E_2^{(0)}+\lambda_2q_2(X),
\]
\[
\ell_{ab}(X)=\ell_0+\beta_\ell |q_a(X)-q_b(X)|,
\qquad
 t_{ab}(X)=t_0\exp[-\alpha_\ell\ell_{ab}(X)].
\]

The R040 associations are `t1=t_V1`, `gamma_d=t_V2`, and `t2=t_12`. The bath parameters `kappa`, `g`, and `bath_onsite` remain explicit independent assumptions unless a later microscopic law derives them.

This law has a useful structural implication. If the selected neighbourhood features at `V` and `1` are equal, then

\[
E_V=E_1,\qquad \gamma_d=t_2,
\]

so the R040 trimer belongs to the exact `V ↔ 1` exchange-symmetric subfamily. The odd state is a BIC candidate only when its energy lies strictly inside the continuum band and the declared bath has no additional open port that couples to it. If the local features differ, no symmetry is enforced and no BIC is tuned into the model by the code.

The law is a *candidate* local rule. In particular, `ell_ab` is a motif-derived barrier proxy, not a measured geometric distance. Its coefficients and energy scale have to be chosen and accepted before a main result. The mapping implementation rejects an unaccepted law.

### Falsification / negative control

Randomly permute the vertex motif assignment while keeping the multiset of four-bit states fixed. This preserves all four bit counts and therefore `K1,K2` exactly, while generally changing ordered local neighbourhood features at the fixed role anchors. Compare the resulting `Phi(X)` values.

A nonzero difference demonstrates that this chosen `Phi` is sensitive to local arrangement rather than only to `K1,K2`. It does **not** demonstrate that the law is physically true or causally realised.

The same check is reported for one actual `full_step` transition `X -> F(X)`. The exporter requires particle counts and `K1,K2` to remain invariant and updates role anchors using the pinned payload map. It never closes a growing orbit into a finite cycle.

## 3. Candidate Psi-A: coherent, event-triggered loading

Let `f(X)` be the concatenated local feature vectors at the three selected roles, evaluated before and after one real carrier step. Define

\[
a_X=\min\left(1,\frac{\|f(FX)-f(X)\|_1}{a_*}\right).
\]

For `a_X>0`, one possible control postulate is

\[
H_c(X)=\Omega_0a_X\bigl(|D_X\rangle\langle B_X|
+|B_X\rangle\langle D_X|\bigr),
\]
\[
u(t)=u_0\sin^2(\pi t/T),\quad 0\le t\le T,
\qquad H(t)=H_0+u(t)H_c(X).
\]

The code integrates the full three-mode Schrödinger equation and records signed net work, gross positive work input, and recovered work separately:

\[
W_{\rm ext}=\int_0^T\langle\psi|\dot H|\psi\rangle dt.
\]

The positive work input is used for conservative fuel accounting; negative work is reported as recovered work and is not silently subtracted unless an explicit recovery efficiency is supplied. The initial bright packet is an input and its preparation cost is separately required in the resource ledger.

## 4. Candidate Psi-B: local-event-gated thermal Davies channel

As a distinct postulate, a separate loading reservoir can induce a downward Bohr transition from a declared bright eigenstate `B` to the direct BIC state `D`:

\[
L_\downarrow(t)=\sqrt{\gamma_0a_Xf(t)}|D\rangle\langle B|,
\]
\[
L_\uparrow(t)=\sqrt{\gamma_0a_Xf(t)e^{-\beta(E_B-E_D)}}
|B\rangle\langle D|.
\]

This is a weak-coupling, Markovian, secular/Davies-type reservoir assumption with detailed balance, `E_B>E_D`, and a gate `f(T)=0`. The loading reservoir is explicitly distinct from the scattering tight-binding bath. The code reports the reservoir heat gained and entropy flow `beta*Q` separately. The gate actuator cost and preparation cost of the initial bright packet remain separate resource inputs; neither is inferred from the heat term.

The Lindblad model is not a free switch: coupling the loading reservoir on and off requires an actuator model, and after the gate is closed the original BIC protection is retested under `H0`.

## 5. Resource ledger and no-double-count rule

Required model inputs include local fuel availability, an explicit energy-per-fuel conversion, precursor stock and consumption, drive efficiency, actuator switching work, controller reset bits, `k_B`, temperature, and initial-packet preparation energy. For the coherent route the ledger uses gross positive control work. For the thermal route it additionally checks reservoir heat/entropy capacity and requires the gate actuator work.

The accounting keeps the following terms separate:

- actuator positive work and switching work;
- controller reset lower bound `k_B T ln(2)` per erased bit;
- initial packet preparation energy;
- heat received by the loading reservoir;
- reservoir entropy flow.

Reservoir heat is **not** added a second time to actuator work. If any required conversion or capacity is absent, the ledger returns `NOT_EVALUABLE`, not `PASS`.

All costs are in declared model units. Nothing here implies an experimentally measured fuel currency or device cost.

## 6. Moving projector and inheritance contract

For each frozen snapshot, `P_X=|D_X><D_X|` is computed from `Phi(X)` without access to future trajectory data. The transfer map is a separate prospective model input

\[
T_X:\mathcal H_X\to\mathcal H_{F(X)},\qquad T_X^\dagger T_X=I_X.
\]

The one-step test is

\[
\|T_X^\dagger P_{F(X)}T_X-P_X\|\le\varepsilon_P.
\]

The identity role-following map is available only as an explicitly accepted assumption; it is never inserted by default. A passing one-step test is not a global stationary BIC on an infinite growing orbit. A global inheritance claim also needs a local prospective rule for `P_X` and `T_X`, and a resource-supported repair mechanism when the identity fails.

## 7. Executable interfaces and statuses

- `x26r040.add_mapping`: pinned carrier verification, local feature export, `Phi`, K-preserving permutation control, and one `F` step.
- `x26r040.transfer`: orthogonal-projector and isometry checks.
- `x26r040.loading`: coherent control evolution with signed/gross work.
- `x26r040.thermal_loading`: separate detailed-balance loading-reservoir model.
- `x26r040.resource_ledger`: fuel/precursor, controller reset, heat and entropy accounting.
- `x26r040.integrated`: optional orchestrator, blocked unless all model assumptions are explicitly accepted and the nested spectral manifest has passed its own runtime preflight.

Default templates are intentionally incomplete. The package cannot mark `ADD_DERIVED` merely because a source hash matches. A digest establishes byte identity, not the truth of a physical postulate.

## 8. What would count as scientific progress

1. Freeze the input word, role anchors, neighbourhood radius, Phi coefficients, and the K-preserving permutation protocol before inspecting the BIC output.
2. Report both the unpermuted and permuted `Phi` outputs, with invariant counts verified.
3. Report direct BIC tests and full spectral controls for the current and next snapshots; no BIC is forced by projection or by fitting after the fact.
4. Freeze one Psi route and its initial state, actuator/reservoir, time grid, work/heat terms, and success threshold before loading.
5. Report the moving-projector test using a declared `T_X`, not one reconstructed from the trajectory.
6. Keep all results labelled `CONDITIONAL_MODEL_NOT_ADD_DERIVED` unless a separate microscopic derivation is supplied.
