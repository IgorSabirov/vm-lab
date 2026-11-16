# B∞ contract — classical AdS5-Schwarzschild thermodynamics and normalization

**ID:** BH1_B_INFINITY_NORMALIZATION_20261116  
**Status:** SOURCE_DEFINED_ANALYTICAL_CONTRACT / NOT_MACHINE_EXECUTED

## 1. Conventions

R is the AdS5 curvature radius and boundary S3 radius. u=(r_+/R)^2. N is the rank. Use the common holographic vacuum energy

E_vac=3*N^2/(16*R).

The total black-hole energy and excitation energy are distinct:

E_B*R = (3*N^2/16)*(1+2*u)^2,
(E_B-E_vac)*R = (3*N^2/4)*u*(1+u).

Entropy:

S_B=pi*N^2*u^(3/2).

The Euclidean action relative to thermal AdS is

I_BH(u)=beta*(F_BH-F_AdS)
       =(pi*N^2/2)*u^(3/2)*(1-u)/(1+2*u).

Temperature:

chi(u)=TR=(1+2*u)/(2*pi*sqrt(u)).

## 2. Exact Hawking-Page checks

At chi_HP=3/(2*pi), the roots are u_SBH=1/4 and u_BBH=1. Then

I_BH(1)=0,
I_BH(1/4)=pi*N^2/32.

At the SBH/BBH fold u=1/2, chi_0=sqrt(2)/pi. The excitation energy there is

(E_B-E_vac)*R = 9*N^2/16,

while the total energy including vacuum is 3*N^2/4. Do not compare a vacuum-subtracted gas energy to the total energy.

At HP the latent heat is Delta E=3*N^2/(2*R).

## 3. Acceptance test: high-energy entropy normalization

Let n=(E_B-E_vac)R. At u>>1,

n~(3*N^2/4)u^2,
S_B~pi*N^2*u^(3/2).

Therefore

S_B~(2^(3/2)*pi/3^(3/4))*sqrt(N)*n^(3/4).

Horowitz–Ooguri eq. (1.2), with V=2*pi^2*R^3, gives exactly the same coefficient. Required test name: B-ENTROPY-ASYMPTOTIC-EXACT.

Regime warning: HO's supergravity spectrum estimate requires n<<lambda^(1/4), while the large-black-hole asymptotic comparison is n>>N^2. Do not imply a controlled common regime in the ordinary classical IIB limit g_s=lambda/(4*pi*N)<<1.

## 4. Required tests

B01 temperature and root identities.
B02 HP action values and barrier.
B03 latent heat.
B04 entropy and area law.
B05 energy/vacuum separation.
B06 B-ENTROPY-ASYMPTOTIC-EXACT.
B07 heat-capacity signs of SBH and BBH.
B08 source/normalization audit.

## 5. Scope

This contract establishes the classical gravity saddle thermodynamics and an exact asymptotic normalization identity. It does not compute the A∞ KK gas, finite-N determinants, real-time kinetics, cosmological nucleation, or BH1/BBN observables.
