# Neighbor review addendum — BH1 K1 / A∞ quantitative checks

**Date:** 2026-11-16  
**Status:** ANALYTICAL REVIEW / CONDITIONAL DERIVATIONS / NO MACHINE RUN  
**Branch:** bh1-ainf-k1-20261116

This addendum records the latest neighbor review and distinguishes source-established facts, algebraic consequences, conditional estimates, and claims that must not be promoted to results. No KK catalogue, thermal partition, BH1 or BBN production calculation was executed in preparing this addendum.

## 1. B∞ entropy normalization: exact asymptotic cross-check

Use the horizon variable u=r_+^2/R^2. In the common holographic vacuum convention,

E_B R = (3N^2/16)(1+2u)^2,
E_vac R = 3N^2/16,
S_B = pi*N^2*u^(3/2).

The excitation energy above thermal AdS is

n := (E_B-E_vac)R = (3N^2/4)u(1+u).

At u >> 1, n ~ (3N^2/4)u^2, so

S_B ~ pi*N^2*(4n/(3N^2))^(3/4)
    = (2^(3/2)*pi/3^(3/4))*sqrt(N)*n^(3/4).

Horowitz–Ooguri eq. (1.2), with V=2*pi^2*R^3 and n=ER in their unit-radius convention, gives the same coefficient:

S_HO=(2/3)^(3/4)*sqrt(2*pi*N)*E^(3/4)*V^(1/4)
    =(2^(3/2)*pi/3^(3/4))*sqrt(N)*n^(3/4).

**Acceptance test B-ENTROPY-ASYMPTOTIC:** exact coefficient equality, with energy measured above the common AdS vacuum. This is an algebraic normalization test, not a new numerical computation.

**Domain warning:** HO's supergravity spectrum estimate also requires n << lambda^(1/4), while the comparison to the large-black-hole asymptotic regime requires n >> N^2. These ranges do not overlap in the ordinary classical IIB regime g_s=lambda/(4*pi*N)<<1 (lambda<<N). Do not use the entropy coefficient to claim a controlled KK-gas calculation at the collapse energy n~N^2. It is an asymptotic cross-check of the B∞ normalization and a formal double-hierarchy comparison, not proof that the KK gas remains valid up to collapse.

## 2. Horowitz–Ooguri spectral asymptotic and catalogue tests

HO eq. (2.2) states the number of single-particle states at energy H=epsilon:

rho_1(epsilon) ~ sum_(l+s=epsilon) l^4*s^3 ~ epsilon^8.

The cumulative number below epsilon therefore scales as N_1(<=epsilon)~epsilon^9. The epsilon^7 claim is not HO's fixed-energy-level density.

HO also state:
- KK levels have multiplicity of order l^4;
- AdS descendants at level s have multiplicity of order s^3;
- singleton representations grow more slowly and do not affect the leading entropy;
- bosonic global-AdS energies are integral, while fermionic modes are half-odd-integral/antiperiodic;
- the supergravity approximation requires n << (g_s N)^(1/4), equivalently n << O(lambda^(1/4)) with convention-dependent 4*pi factors.

Required catalogue tests:
- **A13 integer/half-integer grading:** bosonic one-particle modes must occupy integer global energies; fermionic modes half-odd-integer energies, using the ordinary thermal spin structure.
- **A14 low-level KRN match:** compare every initial KK level, SO(6) representation, field spin, mass/AdS conformal dimension and pure-gauge doubleton removal directly with Kim–Romans–van Nieuwenhuizen (KRN). The epsilon^8 asymptotic cannot detect a wrong low-lying multiplet or an incorrect doubleton subtraction.
- **A15 asymptotic multiplicity:** recover the epsilon^8 power from the complete catalogue without fitting. Do not claim a coefficient until all physical polarizations, descendants, shortening and gauge constraints are explicitly counted.

KRN, Phys. Rev. D 32, 389 (1985), computes the complete mass spectrum of chiral ten-dimensional N=2 supergravity compactified on S5 and identifies the pure-gauge doubleton. The literature spectrum exists; the repository task is to transcribe and organize it into a thermal one-particle catalogue, not to rediscover it. arXiv:1304.1540 is specifically AdS5 x S5/Z3 and must not be cited as the primary unorbifolded S5 spectrum.

## 3. Conditional high-temperature coefficient proposal

The neighbor proposes asymptotic harmonic degeneracies l^4/12 and s^3/6 and a total polarization factor D=256=128_B+128_F. If, and only if, the complete KRN catalogue confirms that this bookkeeping applies without additional level-dependent subtractions, then

rho_1(epsilon) ~ (D/72)*B(5,4)*epsilon^8
              = (D/20160)*epsilon^8.

For D=256 this gives the **conditional hypothesis** c=4/315. The HO paper itself establishes the power, not this coefficient. D=256 must remain a hypothesis to be checked against the explicit catalogue; it is not an accepted input.

If c is the total density and bosons/fermions each contribute c/2 asymptotically, the ordinary thermal trace gives

A = 8!*c*(1-2^(-10))*zeta(10),
ln Z_gas ~ A*chi^9,
E_gas*R ~ 9*A*chi^10,
S_gas ~ 10*A*chi^9.

Under D=256 this yields A~512.0087 and

S_gas(n) ~ [10*A^(1/10)/9^(9/10)] n^(9/10)
         ~ 2.58291*n^(9/10).

This matches the HO exponent n^(9/10), and the coefficient is a falsifiable catalogue check. It is not yet a computed A∞ result. The factor (1-2^-10) assumes equal asymptotic bosonic and fermionic densities; it must be recomputed from separate z_B and z_F if the catalogue does not support that split.

## 4. Collapse scale and lambda hierarchy: conditional only

With the conditional A above, setting E_gas*R~N^2 gives

chi_2^(gas estimate) = (N^2/(9A))^(1/10)
                     ~ 0.43018*N^(1/5).

This coefficient inherits the unverified D=256 normalization and the high-temperature gas approximation. It is not an exact collapse temperature. A different collapse criterion changes the coefficient. Compare energies above the common vacuum: the BBH excitation energy is E_B-E_vac, not E_B including E_vac. The often-quoted 0.75*N^2 at the fold is the total energy including vacuum; the fold excitation energy is 9*N^2/16. Do not mix these when comparing with E_gas, which excludes vacuum.

Using only the leading stringy Hagedorn scale chi_H~lambda^(1/4)/(2*sqrt(2)*pi), the *optional ordering choice* chi_2<chi_H would conditionally require lambda greater than about 2.13e2*N^(4/5). This is not a required consistency condition. In the usual planar limit with fixed large lambda and N increasing, chi_2~N^(1/5) eventually exceeds the fixed chi_H(lambda), consistent with AGGL's discussion that the gas-collapse scale can lie above the string Hagedorn scale in their weak-string-coupling regime. The relative ordering is a property of the joint N,lambda scaling, not a universal law.

At the proposed collapse energy n~N^2, HO's own validity n<<lambda^(1/4) would require lambda>>N^8 (up to convention factors). In the usual classical IIB regime g_s=lambda/(4*pi*N)<<1, lambda<<N. Thus the HO asymptotic KK gas cannot be extrapolated in a controlled way all the way to n~N^2 in that ordinary regime. Keep the parametric T2~N^(1/5) as a gravitational-collapse estimate from AGGL, but quarantine the numerical coefficient 0.43018 and the lambda inequality as conditional extrapolations. AGGL section 2 gives only the order estimate T2~(R*l_p^4)^(-1/5), not the coefficient 0.43018.

## 5. K1 detailed-balance acceptance test

AGGL eqs. (5.3)-(5.4) give, in their matrix-model calculation,

Gamma_(AdS->BBH) = (omega_0/(2*pi))*(K2/K1)*exp[-N^2(Q2-Q1)],
Gamma_(BBH->AdS) = (omega_0/(2*pi))*(K2/K3)*exp[-N^2(Q2-Q3)].

The equilibrium saddle weights are proportional to K1*exp[-N^2 Q1] and K3*exp[-N^2 Q3]. Therefore

P_AdS*Gamma_(AdS->BBH) = P_BBH*Gamma_(BBH->AdS)

at the order retained: both sides are proportional to omega_0*K2*exp[-N^2 Q2]/(2*pi).

**K1 acceptance test:** verify the rate prefactor ratio (K2/K1)/(K2/K3)=K3/K1 against the equilibrium saddle-weight prefactor ratio. Equal exponents at HP alone do not imply equal bare rates. AGGL's full balance statement is equality of equilibrium probability flows, not equality of unweighted rates.

The K_i are Gaussian factors of the phenomenological matrix integral; they are not automatically the complete gravitational one-loop determinants of the full IIB path integral.

## 6. Conditional cosmological nucleation bound

Suppose, as an additional ansatz not derived by AGGL, that a local rate density is

Gamma/V = Acal*T^4*exp(-I_-),

and use the one-Hubble-four-volume completion proxy Gamma/H^4 >= 1. At HP, I_-=pi*N^2/32 and T=chi_HP/R, hence

Gamma/H^4 = Acal*chi_HP^4/(R*H)^4 * exp(-pi*N^2/32).

The proxy gives

R*H <= chi_HP*Acal^(1/4)*exp(-pi*N^2/128).

For Acal=1 this gives:
N=1: 0.46589; N=3: 0.38283; N=5: 0.25850; N=10: 0.04102; N=20: 2.60e-5.

This is a useful conditional constraint to test an embedding, not a derived BH1 law:
- AGGL's matrix-model rate is not itself a local rate per physical four-volume;
- Acal and its N-dependence are unknown;
- Gamma/H^4~1 is a rough one-Hubble-volume criterion, not a full percolation/completion integral;
- a static S3 bounce in a time-dependent FRW background needs a quasi-static/adiabatic justification;
- R=H^-1 and R=a are alternative embedding assumptions, neither selected by this calculation;
- N=1 is outside the controlled large-N semiclassical regime.

For R=H^-1, RH=1, the proxy fails for Acal=1 at HP for every listed N. This does **not** prove no transition for all possible prefactors or histories. It also does not prove that the system must switch exactly at a spinodal. Nucleation is nonzero before the spinodal; the switching point depends on the integrated hazard. A spinodal is the loss of local metastability, not a universal deterministic trigger.

## 7. Updated scientific disposition

- K1 classical action/barrier and AGGL's source-defined semiclassical rate structure: analytically source-verified.
- Detailed-balance prefactor relation: exact within the AGGL saddle approximation; add as an acceptance test.
- B∞ entropy asymptotic coefficient: exact algebraic normalization test; add to B contract.
- HO rho~epsilon^8 and S~n^(9/10): source-verified.
- D=256 coefficient c=4/315, A~512.0087, chi2 coefficient 0.43018 and lambda~213*N^(4/5): conditional hypotheses/estimates pending exact catalogue and regime audit.
- Cosmological nucleation bound: conditional dimensional estimate only, not a derived kinetic law or a physical restriction on R_embedding.
- No physical null among sector_X, R_embedding, N/lambda, complete_free_energy, transition_trigger, kinetic_law or collision_terms is fully closed by this addendum.
