# BH1 development review: A_infinity, K1 and the corrected branch map

**Date:** 2026-11-16  
**Status:** ANALYTICAL_SOURCE_REVIEW / CONTRACTS_PROPOSED / NO_EXECUTION  
**Branch:** bh1-ainf-k1-20261116  
**Base:** f10f4d742af50fa6834287fab57921dfaffae1dd  
**Purpose:** incorporate the supplied neighbor review, separate source-established results from phenomenological modelling, and replace the weak-to-strong A/B matching task with the same-coupling strong-coupling pair A_infinity/B_infinity.

## 1. Main correction

The missing strong-coupling confined saddle is not an extrapolation of the free branch A' at lambda=0. It is thermal AdS with the thermal gas of type-IIB supergravity modes on global AdS5 x S5. It shares the same conformal boundary S1_beta x S3_R with the AdS-Schwarzschild saddles. In the canonical ensemble, thermal AdS and the big black hole are the two locally stable competing saddles; the small black hole is unstable and acts as the Euclidean bounce/thermalon.

Use three distinct labels:

- A' = free, zero-coupling confined branch (the earlier letter-function calculation).
- A_infinity = strong-coupling thermal AdS, including the full supergravity KK gas and the common vacuum convention.
- B_infinity = large AdS5-Schwarzschild black hole.

The old empty-domain result remains valid only for A' versus B_infinity. It is not a no-go for A_infinity versus B_infinity. The latter pair has a common boundary and a Hawking-Page coexistence point.

## 2. Source review: what is established

### 2.1 Classical gravity thermodynamics

Let u=(r_+/R)^2. Do not use x for both the horizon ratio and the Polyakov-loop variable.

The black-hole temperature is

chi(u)=TR=(1+2u)/(2*pi*sqrt(u)).

At fixed chi above chi_0=sqrt(2)/pi, the two roots are

u_-(chi)=[(pi*chi-sqrt(pi^2*chi^2-2))/2]^2,
u_+(chi)=[(pi*chi+sqrt(pi^2*chi^2-2))/2]^2.

The minus root is the small black hole (negative heat capacity); the plus root is the big black hole (positive heat capacity).

In the common AdS-vacuum-subtracted convention, the on-shell action difference is

I_BH(u)=beta*(F_BH-F_AdS)
       =(pi*N^2/2)*u^(3/2)*(1-u)/(1+2*u).

At u=1, chi_HP=3/(2*pi), I_BH=0. At the same temperature, u_-=1/4 and

I_SBH(chi_HP)=pi*N^2/32.

The black-hole fold is chi_0=sqrt(2)/pi at u=1/2. The maximum supercooling interval for a metastable big black hole, measured relative to chi_HP, is

1-chi_0/chi_HP = 1-2*sqrt(2)/3 = 0.0571909584...

The action formula above is an **on-shell gravitational action as a function of horizon radius**. It is not, by itself, the off-shell Polyakov-loop effective potential or a Lorentzian equation of motion.

### 2.2 Tunnelling and the role of the small black hole

Alvarez-Gaume, Gomez, Liu and Wadia (AGGL) give the semiclassical bounce interpretation and rates. In their notation the small black hole is the unstable saddle between thermal AdS and the BBH. Schematically,

Gamma_(AdS->BBH) ~ (omega_0/(2*pi))*(K_2/K_1)*exp(-I_-),
Gamma_(BBH->AdS) ~ (omega_0/(2*pi))*(K_2/K_3)*exp(-(I_--I_+)).

Here I_- and I_+ are the small- and big-black-hole on-shell Euclidean actions; K_i are Gaussian factors in the AGGL phenomenological matrix integral and omega_0 is the unstable-mode frequency used in their two directional rates. The gravity discussion separately denotes determinant prefactors A_1,A_2. Do not identify the matrix-model K_i automatically with complete gravitational one-loop determinants.

At chi_HP, I_+=0, so the two exponential suppression factors have the same exponent pi*N^2/32. This does **not** justify setting the full rates equal by dropping their determinant/frequency prefactors. Detailed balance applies to the complete equilibrium weights and rates.

For N large, the bounce is exponentially suppressed near coexistence. For example, the exponent at coexistence is pi*N^2/32. A system can therefore remain metastable below/above the equilibrium transition, depending on its history and available time. It is not correct to claim that every transition must occur exactly at chi_HP. Nor is it correct to claim that every transition must wait until a spinodal: thermal nucleation is nonzero before the spinodal. The actual switching point requires a rate prefactor and a time-volume integral.

### 2.3 The AGGL effective action is phenomenological

AGGL explicitly describe their (a,b) matrix model as a phenomenological truncation/universality-class model. The coefficients of the full finite/strong-coupling SYM effective action are not known there. Their order parameter is the Polyakov-loop eigenvalue distribution; rho_1=(1/N)Tr U and the matrix variable m=(1/N^2)Tr U Tr U^dagger are not the horizon ratio u.

The paper matches the on-shell actions of SBH and BBH to selected matrix-model saddle actions in the strong-coupling limit. It does not derive an exact microscopic Lorentzian kinetic law for the full N=4 SYM theory.

Therefore K1 may freeze the source-derived saddle/bounce structure and its conditional semiclassical rates. It must not label the AGGL phenomenological potential as an exact microscopic potential, and must not promote Euclidean tunnelling estimates into a cosmological real-time law.

### 2.4 Finite-N saddle weights and f

Near the Hawking-Page crossover, AGGL obtain a two-saddle partition sum of the form

Z ~= K_1 + K_3*exp(nu*t),  t=N^2*(T-T_HP)/T_HP,

to the stated asymptotic order, with nu fixed by the latent heat. The order-parameter expectation interpolates with the same saddle weights.

Thus the candidate saddle probability is

f_BH = K_3*exp(nu*t)/(K_1+K_3*exp(nu*t)),

not a bare logistic unless K_1/K_3 is explicitly set to one. The user's simplified logistic is the leading exponential shape; determinant factors shift its center at order 1/N^2. This f_BH is a canonical saddle weight, not a spatial volume fraction and not an independent collective coordinate. The Polyakov-loop order parameter remains a separate observable.

### 2.5 Thermal gas, Hagedorn and gravitational collapse are three different limits

The A_infinity thermal gas is a gas of supergravity KK modes on global AdS5 x S5. Horowitz-Ooguri derive a polynomial single-particle density, asymptotically rho(epsilon)~epsilon^8, and a gas entropy S~(ER)^(9/10). Polynomial one-particle growth implies convergence of the ordinary bosonic/fermionic thermal trace for every q=exp(-beta/R)<1. Therefore the **supergravity KK gas by itself has no finite-temperature Hagedorn singularity**.

This statement is restricted to the supergravity KK spectrum. It does not remove the stringy Hagedorn temperature of the full type-IIB string spectrum. At strong 't Hooft coupling, the latter grows parametrically as

T_H*R = lambda^(1/4)/(2*sqrt(2)*pi) + 1/(2*pi) + O(lambda^(-1/4)),

with higher corrections available in the strong-coupling world-sheet/effective analysis. This is a string-oscillator/winding-sector result, not a KK-gas result.

There is a third scale: the thermal supergravity gas eventually collapses gravitationally into a black hole. The estimate is T_2~(R*l_p^4)^(-1/5), hence T_2*R~N^(1/5) at leading scaling using R/l_p~N^(1/4). This is an energy/backreaction threshold, not a Hagedorn divergence.

The AGGL thermal-AdS Hagedorn singularity is described in their effective model as a merger of the thermal-AdS and SBH saddles (A3 cusp). It must not be misidentified with a divergence of the free KK gas.

The four relevant temperatures are therefore distinct:
- chi_0=sqrt(2)/pi: BBH/SBH fold;
- chi_HP=3/(2*pi): thermal-AdS/BBH coexistence;
- chi_H(lambda): stringy Hagedorn/A3 limit of thermal AdS;
- chi_2(N)~N^(1/5): gravitational collapse of the thermal gas.

Do not hard-code an ordering between chi_H and chi_2 without specifying the joint large-N/large-lambda hierarchy.

## 3. A_infinity: the actual strong-coupling confined branch

The leading classical vacuum contribution is E_vac=3*N^2/(16*R) in the common holographic convention. Thermal AdS has no classical temperature-dependent entropy; the first temperature-dependent contribution comes from the quantum thermal gas and is O(N^0).

Define the ordinary canonical gas partition function, not a supersymmetric index:

Z_gas = product over bosonic modes (1-exp(-beta*omega_j))^(-d_j)
        times product over fermionic modes (1+exp(-beta*omega_j))^(d_j),

or equivalently

ln Z_gas = sum_(m>=1) [z_B(q^m)+(-1)^(m+1)*z_F(q^m)]/m,
q=exp(-beta/R).

Then

F_Ainf = E_vac - T*ln Z_gas,
E_Ainf = E_vac + E_gas,
S_Ainf = S_gas,
C_V,Ainf = C_V,gas,

at the stated leading supergravity/one-loop order. The same vacuum subtraction must be used for B_infinity. The common additive vacuum energy cancels in the free-energy difference and in the bounce exponent, but it must remain in absolute energy accounting for the cosmological bridge.

The complete unorbifolded S5 KK mass spectrum is already known in KRN (1985); HO provide the AdS descendant counting. What is not yet assembled in this repository is a machine-readable thermal catalogue with exact degeneracies, descendants, boson/fermion grading and doubleton/gauge subtraction. A_infinity is therefore source-defined but not yet numerically reconstructed.

## 4. Revised branch logic

- A' versus B_infinity: no common chi-domain at common R; retain as a regime-mismatch result only.
- A_infinity versus B_infinity: same strong-coupling theory, same S1_beta x S3_R boundary, common vacuum convention, coexistence at chi_HP. This is the correct pair for the strong-coupling thermodynamic bridge.
- A_infinity requires the full thermal KK gas. The gas correction shifts the coexistence temperature at order N^-2. At first order, if the gas is the only O(N^0) correction retained,

delta_chi_c = 3*ln(Z_gas(chi_HP))/(2*pi^2*N^2) > 0.

This is a conditional leading correction; black-hole one-loop determinants and other O(N^0) effects must be included before calling it the complete finite-N shift.
- K1 gives a source-based Euclidean bounce/rate structure. It does not yet supply a physical cosmological time variable, rate prefactor, volume growth, or coupling to photons/neutrinos.

## 5. Null status after this review

No physical null is fully closed.

- sector_X: unchanged.
- R_embedding: the old kappa bound applies only to comparing A' and B_infinity; it is not required for A_infinity/B_infinity with common boundary.
- N, lambda: asymptotic regimes and scaling known; numerical values and joint hierarchy remain open.
- complete_free_energy: common vacuum convention and the A_infinity gas construction specified; complete KK sum and finite-lambda corrections remain open.
- transition_trigger: canonical Euclidean bounce and spinodal structure supplied conditionally by AGGL; cosmological trigger/history not derived.
- kinetic_law: semiclassical rates have source-defined exponential structure, but determinants, real-time dynamics, cosmological rate integration and backreaction remain open.
- collision_terms: no portal Lagrangian or collision operator.
- initial_state and cosmological_perturbations remain open.

## 6. Work order

1. Freeze K1 source reconstruction: distinguish on-shell gravity action from the phenomenological Polyakov-loop effective potential; derive roots, actions, barrier, spinodals, and rate prefactors as far as sources permit. No dynamics claim beyond the Euclidean canonical calculation.
2. Freeze A_infinity spectrum contract: full KK multiplets, energies, degeneracies, boson/fermion statistics, thermal spin structure, vacuum convention, convergence and output requirements.
3. Only after the spectrum is assembled, compute Z_gas, E, S, C_V, and the O(N^-2) coexistence shift.
4. Reassess BH1 physical embedding only after the same-theory thermodynamic pair is established.

No BH1, BBN, S2 or VM production run was started by this update. The prior free-branch result artifacts have been corrected by an erratum on this branch; the old unsupported numerical rows are quarantined.


## 7. Latest neighbor review: quantitative additions and caveats

The full claim-by-claim disposition is in [NEIGHBOR_REVIEW_ADDENDUM_20261116.md](NEIGHBOR_REVIEW_ADDENDUM_20261116.md). Important additions:

- B∞ now has a separate [B_INFINITY_CONTRACT.md](B_INFINITY_CONTRACT.md). Its high-energy entropy coefficient agrees exactly with Horowitz–Ooguri after using excitation energy above the common AdS vacuum:
  `S_B ~ (2^(3/2)*pi/3^(3/4))*sqrt(N)*n^(3/4)`.
- HO's fixed-level single-particle density is `rho_1(epsilon)~epsilon^8`; the cumulative count is `~epsilon^9`. The `epsilon^7` claim is not the HO density.
- The exact low-level KRN match and integer/half-integer boson/fermion grading are now explicit catalogue acceptance tests. The leading epsilon^8 test alone cannot catch a bad doubleton subtraction or a wrong low-lying mode.
- The proposed coefficient `D=256`, `c=4/315`, `A~512.0087` and `chi_2~0.43018*N^(1/5)` remain conditional until the full spectrum verifies the polarization bookkeeping. HO gives the power, not this coefficient.
- HO's validity condition `n<<lambda^(1/4)` must not be dropped. At `n~N^2`, the proposed collapse extrapolation is outside the ordinary classical IIB supergravity hierarchy; do not call the numerical collapse coefficient a controlled KK result.
- K1 now has an operational detailed-balance test: the rate prefactor ratio must equal the equilibrium saddle-weight prefactor ratio. Equality of bare rates does not follow from equality of exponents.
- A cosmological nucleation estimate `R*H <= chi_HP*Acal^(1/4)*exp(-pi*N^2/128)` is recorded only as a conditional dimensional proxy. AGGL does not derive the assumed local FRW rate density `Acal*T^4*exp(-I_-)`. It cannot close R_embedding or kinetic_law.
- Nonzero nucleation can occur before a spinodal. A spinodal is loss of metastability, not an automatic transition time. The actual switch requires a time-integrated hazard and backreaction.

No KK catalogue or thermal sum was executed in this update. No BH1/BBN run was started; main remains untouched.
