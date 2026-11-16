# BH1 null-closure status — consolidated development history

**Date:** 2026-11-16  
**Branch:** bh1-ainf-k1-20261116  
**Status:** 0/8 fully closed; 3/8 materially narrowed; 5/8 open.  
**Scope:** source-level and analytical progress only. No BH1/BBN production run. Peer-supplied machine results are identified as such and are not repository executions.

## Executive result

The thermodynamic architecture is substantially more constrained than the original bridge, but no original physical null is fully closed. The strongest progress is:
1. Correct strong-coupling thermodynamic pair identified: A_infinity (thermal AdS plus IIB supergravity KK gas) and B_infinity (large AdS5-Schwarzschild).
2. K1 Euclidean saddle/bounce structure, barrier and detailed-balance prefactor relation source-checked.
3. B_infinity entropy normalization independently matched algebraically to Horowitz–Ooguri.
4. A_infinity Weyl-law backbone derived and the k=2 thermal-character defect identified.
5. The weak-coupling A' and strong-coupling A_infinity branches are explicitly kept separate.

This is progress in the model's thermodynamic and representation-theory infrastructure, not yet a physical cosmological realization.

## Null-by-null ledger

| Null | Status | What is actually established | What closes it |
|---|---|---|---|
| sector_X | OPEN | AGGL saddle weight, Polyakov-loop order parameter and spatial volume fraction are distinct objects. No cosmological X identity follows. | Specify X as a physical sector/field content; define f operationally; derive its coupling and observable degrees of freedom. |
| R_embedding | OPEN | A_infinity/B_infinity share the same boundary S1_beta x S3_R. The old kappa bound applies only to the mismatched A'/B_infinity comparison. A conditional FRW nucleation proxy exists, but its local rate ansatz is not derived. | Derive R(t) relative to a(t), H(t), and the actual rate in an expanding geometry; integrate the completion probability. |
| N, lambda | PARTIALLY CONSTRAINED | lambda=0 and lambda>>1 regimes are separated. HO validity n<<lambda^(1/4) makes the proposed n~N^2 KK-collapse extrapolation incompatible with ordinary classical IIB lambda<<N. | Select a controlled joint large-N/large-lambda hierarchy and determine N, lambda from an independent physical principle or data. |
| complete_free_energy | PARTIALLY CONSTRAINED | Common vacuum convention fixed; B_infinity classical thermodynamics and entropy normalization checked; A_infinity Weyl asymptotic established. The positive-only k=2 thermal sum is invalid; signed-subtraction peer values remain provisional. | Derive the physical shortened k=2 character; validate k=1 doubleton removal and k=2,3,4 against KRN; rebuild z_B,z_F and compute the full gas sum; add BBH one-loop determinant and finite-lambda corrections. |
| kinetic_law | PARTIALLY CONSTRAINED | K1 supplies source-level Euclidean bounce exponent pi*N^2/32 at HP and forward/reverse saddle-rate structure. Detailed balance applies to full equilibrium flows including prefactors, not bare rates. | Compute physical determinants/prefactors; derive local rate density, Lorentzian growth/reverse law, FRW integrated hazard and backreaction. |
| collision_terms | OPEN | No portal Lagrangian or collision operator is present. Thermodynamic and geometric constraints do not supply microscopic interactions. | Specify portal Lagrangian; derive collision integrals, signs, detailed balance, and decoupling/energy-transfer limits. |
| initial_state | OPEN | K1/A_infinity do not select cosmological initial conditions. | Specify initial T,R,H, X abundance, saddle/order parameter, entropy and cosmological branch. |
| cosmological_perturbations | OPEN | No perturbation dynamics or transfer functions have been derived. | Derive coupled perturbation equations, isocurvature/transfer functions and compare with CMB/structure constraints. |

Separate auxiliary null transition_trigger: PARTIALLY CONSTRAINED. The equilibrium saddles, Euclidean bounce and spinodal endpoints are known. Nucleation can occur before a spinodal; a spinodal is loss of metastability, not an automatic switching time. The cosmological history that brings the system to a transition remains unknown.

## Accepted source-level/analytical results

### K1
At Hawking–Page, with u=(r_+/R)^2, the small and large black-hole roots are u_-=1/4 and u_+=1. The small-hole on-shell action is

I_-= (pi*N^2/2)*(u^(3/2)*(1-u)/(1+2*u)) at u=1/4 = pi*N^2/32.

AGGL's matrix model is phenomenological. Its Euclidean bounce/rate structure is not an exact microscopic Lorentzian law. The detailed-balance test is equality of equilibrium probability flows after including saddle prefactors.

### B_infinity
The large-black-hole entropy asymptotic coefficient matches Horowitz–Ooguri exactly when energy is measured above the common AdS vacuum. This is an algebraic normalization test, not a machine run.

### A_infinity
HO gives fixed-level density rho_1(epsilon)~epsilon^8; cumulative count scales as epsilon^9. The 10D Weyl derivation with D=256 gives cumulative coefficient 256/181440, continuous density 4/315 and discrete half-step level count 2/315.

The reported RS multiplet identity dim M_k=256 dim[0,k-2,0] for k=2..46 is peer-reported, not independently re-executed in this repository. The k=2 positive-only thermal implementation counted 291 rather than 256 and is invalid as implemented. Peer signed-subtraction thermodynamic values are provisional pending explicit shortened-character/null-submodule derivation and KRN component match. A14 is partial; A15 is trend-only pending tolerance and full primary-tower tail control.

## Conditional results — not accepted as physical predictions

- D=256 -> c=4/315 and A=512.008725... depends on complete polarization bookkeeping and equal asymptotic boson/fermion densities.
- chi_2~0.43018 N^(1/5) is an extrapolation of the high-temperature KK gas into a regime where HO supergravity validity n<<lambda^(1/4) fails at n~N^2 in ordinary classical IIB scaling.
- lambda~213 N^(4/5) is only an optional ordering condition chi_2<chi_H, not a universal consistency law.
- The FRW bound RH<=chi_HP Acal^(1/4) exp(-pi*N^2/128) assumes a local rate density Acal T^4 exp(-I_-) and a one-Hubble-four-volume completion proxy. Neither is derived by AGGL; this does not close R_embedding or kinetic_law.
- Finite-N crossover scale O(N^-2) is not automatically a midpoint shift. The midpoint depends on the full ratio of thermal-AdS and BBH one-loop saddle prefactors.

## Provenance and execution discipline

- Peer-reported KK computations remain labelled peer-reported; they are not claimed as repository machine runs.
- Previous A' numerical artifacts remain quarantined by the existing erratum.
- No new machine execution, VM job, BH1 run or BBN run is claimed here.
- No scientific acceptance is granted.
- main is not modified.

## Critical next block

The next critical block is A_infinity A14, not cosmological kinetics:

1. Derive the physical shortened k=2 massless character with explicit gauge/null-submodule subtraction.
2. Match k=2,3,4 component-by-component to KRN; justify k=1 doubleton omission.
3. Rebuild z_B,z_F from validated physical characters.
4. Recompute Z_gas, F, E, S, C_V with independent derivative checks.
5. Extend k_max or prove omitted-primary tail bounds and set an A15 tolerance.
6. Then compute the BBH one-loop determinant for the full finite-N midpoint.
7. Only after that return to FRW kinetics, R_embedding and collision terms.
