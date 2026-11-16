# K1 contract — Hawking-Page saddles, Euclidean bounce and finite-N crossover

**ID:** BH1_K1_HP_SADDLE_BOUNCE_20261116  
**Status:** SOURCE_REVIEWED_ANALYTICAL_CONTRACT / NOT_MACHINE_EXECUTED  
**Scope:** source reconstruction for global AdS5-Schwarzschild thermodynamics and the AGGL canonical effective model. No cosmological dynamics claim.

## 1. Notation lock

- R: common AdS curvature radius and boundary S3 radius.
- chi=TR.
- u=r_+/R: black-hole horizon parameter.
- rho_1=(1/N)Tr U: Polyakov-loop order parameter.
- m=(1/N^2)Tr U Tr U^dagger: nonnegative matrix-model variable.
- mu, g: AGGL auxiliary saddle variables.
- Never use the same symbol x for u and a Polyakov-loop variable.

## 2. Classical saddle geometry

chi(u)=(1+2u^2)/(2*pi*u).

For chi>=chi_0=sqrt(2)/pi,

u_-(chi)=(pi*chi-sqrt(pi^2*chi^2-2))/2,
u_+(chi)=(pi*chi+sqrt(pi^2*chi^2-2))/2.

u_- is the small, negative-specific-heat saddle; u_+ is the big, positive-specific-heat saddle.

The common-vacuum-subtracted on-shell action is

I_BH(u)=beta*(F_BH-F_AdS)
       =(pi*N^2/2)*u^3*(1-u^2)/(1+2*u^2).

Required exact checks:
- chi_0=sqrt(2)/pi at u=1/sqrt(2).
- chi_HP=3/(2*pi) at u=1.
- At chi_HP: u_-=1/2, u_+=1.
- I_BH(u_+)=0 at u=1.
- I_SBH(chi_HP)=pi*N^2/32.
- Latent heat at coexistence Delta E=3*N^2/(2*R).
- chi_HP-chi_0=(3-2*sqrt(2))/(2*pi).
- Maximum BBH supercooling fraction 1-chi_0/chi_HP=1-2*sqrt(2)/3.

## 3. Euclidean bounce and rates

The SBH is the unstable Euclidean bounce/thermalon separating the thermal-AdS and BBH saddles. Record the two directions separately:

Gamma_(AdS->BBH) ~ (omega_0/(2*pi))*(K_2/K_1)*exp(-I_-),
Gamma_(BBH->AdS) ~ (omega'_0/(2*pi))*(K_2/K_3)*exp(-(I_--I_+)).

The K_i are Gaussian factors of the AGGL phenomenological matrix integral and omega_0 is the unstable-mode frequency in that calculation. The source supplies this structure, not complete numerical factors for our target implementation and not automatically the complete gravitational one-loop determinants of the full IIB path integral.

At coexistence, both exponents reduce to I_-=pi*N^2/32. Do not infer equality of the full rates from equality of exponents; retain prefactors and detailed balance. AGGL eqs. (5.3)-(5.4) use the same unstable-mode frequency omega_0 and Gaussian factors K2/K1 and K2/K3. Their equilibrium saddle weights carry prefactors K1 and K3. Thus P_AdS*Gamma_(AdS->BBH)=P_BBH*Gamma_(BBH->AdS) at the order retained; both flows are proportional to omega_0*K2*exp(-N^2*Q(mu2))/(2*pi).

Required distinctions:
- Nonzero thermal nucleation is possible before a spinodal.
- At large N the coexistence barrier is O(N^2), so the rate is exponentially suppressed.
- The actual transition temperature in a finite-time system depends on prefactors, spatial volume, time history and rate integration.
- The spinodal is a loss of local metastability, not a universal deterministic cosmological trigger.
- No Lorentzian equation of motion or FRW rate integral is supplied by this contract.

## 4. AGGL matrix model boundary

The AGGL (a,b) model is phenomenological. Its effective potential Q(mu) and Polyakov-loop variables are not identical to I_BH(u). The latter is the on-shell Euclidean action evaluated on a gravity saddle.

Record the AGGL finite-N two-saddle crossover in its source form:

Z ~= K_1 + K_3*exp(nu*t),
t=N^2*(T-T_HP)/T_HP,

and

f_BH = K_3*exp(nu*t)/(K_1+K_3*exp(nu*t)).

For the AdS5 x S5 HP latent heat, nu=pi at leading order. Equivalently the leading exponent is (2*pi^2/3)*N^2*(chi-chi_HP). K_1/K_3 must be retained unless explicitly set by a justified approximation. This f_BH is a canonical saddle weight, not a volume fraction and not an independent dynamical coordinate. The Polyakov-loop expectation is a separate order parameter.

## 5. Temperature landmarks

- chi_0=sqrt(2)/pi: BBH/SBH fold (A2).
- chi_HP=3/(2*pi): Hawking-Page coexistence.
- chi_H(lambda): thermal-AdS stringy Hagedorn/A3 saddle merger; not the supergravity KK gas pole.
- chi_2(N)~N^(1/5): gravitational collapse threshold of the thermal gas.

Do not order chi_H and chi_2 without stating the joint N,lambda hierarchy.

## 6. Required tests

K1-T01: exact root formula and branch labels.
K1-T02: reproduce chi_0 and chi_HP.
K1-T03: reproduce the two actions and the HP barrier.
K1-T04: reproduce the latent heat from the derivative of the on-shell free-energy difference.
K1-T05: verify the BBH heat-capacity sign and the SBH negative sign.
K1-T06: verify the two rate exponents and keep the determinant/frequency prefactors symbolic.
K1-T07: derive the 5.72% maximum BBH supercooling interval.
K1-T08: reproduce the finite-N two-saddle crossover including K_1/K_3.
K1-T09: verify the A3 thermal-AdS merger is distinct from the free KK-gas partition function.
K1-T10: source/notation audit; no Yaffe attribution without a precise verified reference.
K1-T11 detailed balance: verify (K2/K1)/(K2/K3)=K3/K1 equals the equilibrium saddle-weight prefactor ratio. Keep the common unstable-mode frequency and the exponential saddle actions. This is an operational check of the rate derivation, not a claim that bare forward and reverse rates are equal.
K1-T12 finite-N midpoint: retain K1 and K3 in the two-saddle sum. Define the crossover characteristic scale from the coefficient of N^2*(chi-chi_HP); do not call it a universal 10-90% width or a shift of the midpoint.
K1-T13 conditional FRW nucleation estimate: if an additional local rate-density ansatz Gamma/V=Acal*T^4*exp(-I_-) and a one-Hubble-four-volume proxy Gamma/H^4>=1 are assumed, reproduce R*H<=chi_HP*Acal^(1/4)*exp(-pi*N^2/128). Mark this as CONDITIONAL_ESTIMATE_ONLY. It is not a rate density derived by AGGL and is not a cosmological kinetic law.

## 7. Acceptance

A pass establishes the classical saddle and source-defined Euclidean bounce structure, plus the stated phenomenological finite-N crossover. It does not establish a microscopic exact SYM effective potential, complete gravitational determinant prefactors, a local FRW rate density, real-time cosmological kinetics, or a physical BH1 trigger. Nonzero thermal nucleation can occur before a spinodal; the actual switching point requires the integrated hazard and cannot be set equal to the spinodal by assertion.
