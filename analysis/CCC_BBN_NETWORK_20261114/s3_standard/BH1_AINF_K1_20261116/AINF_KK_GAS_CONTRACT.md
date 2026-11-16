# A_infinity contract — thermal AdS supergravity KK gas

**ID:** BH1_AINF_KK_GAS_20261116  
**Status:** SOURCE_SPECIFIED / CATALOG_NOT_ASSEMBLED / THERMAL_SUM_NOT_COMPUTED  
**Theory:** planar/large-N, strongly coupled N=4 SU(N) SYM on S3_R x S1_beta, dual to type-IIB supergravity on global AdS5 x S5.

## 1. Physical branch

A_infinity is thermal AdS with the full thermal gas of type-IIB supergravity Kaluza-Klein modes. It is not the zero-coupling free letter-gas branch A'. It shares the same boundary S1_beta x S3_R with B_infinity.

Fix:
- Gauge theory: SU(N), large N.
- Ensemble: ordinary canonical thermal trace, zero chemical potentials.
- Fermions: thermal antiperiodic spin structure; use Fermi-Dirac plus signs in the oscillator partition function. Do not compute a supersymmetric index or insert (-1)^F.
- Geometry: global AdS5 x S5 with common radius R.
- Vacuum convention: leading holographic E_vac=3*N^2/(16*R). State separately the finite-N SU(N) correction if included; do not mix it with the leading classical supergravity result.
- Scope: supergravity KK spectrum only. Massive string oscillator modes are excluded from Z_gas and enter separately through finite-lambda/string corrections and the stringy Hagedorn scale.

## 2. Spectrum input

Build a machine-readable complete one-particle spectrum table. Each row must identify:
- KK supermultiplet/tower label and level;
- 5d field and spin;
- SU(4)_R representation;
- AdS5 lowest energy / conformal dimension;
- all descendant energy levels;
- bosonic or fermionic statistics;
- exact degeneracy at every energy;
- gauge constraints, shortening conditions and singleton/doubleton subtraction;
- primary source and equation/table locator.

The spectrum must include the complete type-IIB supergravity multiplet tower on S5, not only the chiral-primary scalar tower and not only protected scalar primaries. Include all bosonic and fermionic descendants with correct multiplicities.

The source-level asymptotic check is polynomial one-particle growth rho_1(epsilon)~epsilon^8 (Horowitz–Ooguri eq. 2.2). This establishes convergence behavior but does not replace the exact finite-level spectrum table. The singleton/doubleton sector grows more slowly and does not change the leading power, but it must still be treated correctly in the low-level catalogue.


## 2A. Source-defined spectrum checks and conditional coefficient hypothesis

KRN (Phys. Rev. D 32, 389 (1985)) is the primary source for the complete IIB supergravity mass spectrum on S5 and the pure-gauge doubleton. HO (hep-th/9802116), eqs. (1.3), (2.2)-(2.3), provide the AdS descendant counting, integer/half-integer grading and the validity range. arXiv:1304.1540 is specifically the orbifold S5/Z3 and is not the primary unorbifolded S5 spectrum.

HO's asymptotic statement is rho_1(epsilon)~epsilon^8. It follows from KK multiplicity ~l^4 and AdS descendant multiplicity ~s^3 with l+s=epsilon. The cumulative count scales as epsilon^9.

A possible coefficient reconstruction is to use asymptotic factors l^4/12 and s^3/6 and a total polarization factor D. This gives c=D/20160. The proposed D=256 (128 bosonic plus 128 fermionic physical polarizations) is a **hypothesis pending the complete KRN catalogue**, not a source-established coefficient. If confirmed, c=4/315.

If c is the total density and the boson/fermion high-energy densities are equal, the ordinary thermal trace gives

A=8!*c*(1-2^(-10))*zeta(10),
ln Z_gas~A*chi^9,
E_gas*R~9*A*chi^10,
S_gas~10*A*chi^9.

For D=256 this conditional estimate is A~512.0087 and S_gas(n)~2.58291*n^(9/10). These numbers are catalogue validation targets, not computed A∞ outputs. The factor (1-2^(-10)) assumes equal asymptotic bosonic and fermionic densities; recompute it from z_B and z_F if that assumption fails.

The HO validity window n<<lambda^(1/4) must be enforced. Do not extrapolate the high-energy KK gas to n~N^2 collapse without separately checking this bound and the string-loop regime. In ordinary classical IIB supergravity, g_s=lambda/(4*pi*N)<<1 also imposes lambda<<N, so the simultaneous hierarchy n~N^2<<lambda^(1/4) is not available at large N. This blocks treating the conditional chi_2 coefficient as a controlled KK-gas prediction.

## 3. Thermal partition function

For q=exp(-beta/R)=exp(-1/chi), define

z_B(q)=sum over bosonic one-particle modes d_j*q^(R*omega_j),
z_F(q)=sum over fermionic one-particle modes d_j*q^(R*omega_j).

Then

ln Z_gas(chi)=sum_(m>=1) [z_B(q^m)+(-1)^(m+1)*z_F(q^m)]/m.

Equivalently, use the product over Bose and Fermi oscillators. No chemical potentials and no index insertion.

Derive:
- F_gas=-T*ln Z_gas;
- E_gas=-d(ln Z_gas)/d beta;
- S_gas=ln Z_gas+beta*E_gas;
- C_V,gas=dE_gas/dT at fixed R.

The strong-coupling confined branch is

F_Ainf=E_vac+F_gas,
E_Ainf=E_vac+E_gas,
S_Ainf=S_gas,
C_V,Ainf=C_V,gas.

## 4. Convergence and domain

HO eq. (2.2) gives the fixed-energy single-particle level density rho_1(epsilon)~epsilon^8, while the cumulative count below epsilon scales as epsilon^9. The power epsilon^7 is not the HO fixed-level density. The one-particle density grows polynomially, so z_B(q), z_F(q), and the ordinary free-gas thermal trace converge for every 0<q<1 (positive temperature). HO also states that bosonic global-AdS energies are integers and fermionic modes are half-odd-integers/antiperiodic. The supergravity approximation requires n<<lambda^(1/4) up to convention-dependent 4*pi factors. There is no finite-chi Hagedorn pole in the supergravity KK gas alone.

This does not imply that the full string theory has no Hagedorn temperature. The string oscillator/winding sector has a separate Hagedorn scale chi_H(lambda) which grows as lambda^(1/4) at strong coupling. The AGGL A3 merger of thermal AdS and SBH is a full string/large-N saddle phenomenon, not a divergence of the truncated KK gas.

A further high-energy limit is gravitational collapse of the thermal gas. The estimate T_2~(R*l_p^4)^(-1/5) gives chi_2~N^(1/5) at leading scaling. This is a backreaction/collapse threshold, not a Hagedorn singularity. Keep chi_H(lambda) and chi_2(N) as separate cutoffs; compare them only after fixing a joint N,lambda hierarchy.

## 5. Vacuum and Hawking-Page matching

Use the same E_vac convention for A_infinity and B_infinity. The common vacuum term cancels from F_B-F_A and from the leading Euclidean action difference, but it remains in absolute energy and gravitational sourcing.

At classical leading order, F_B-F_A=0 at chi_HP=3/(2*pi). The thermal gas adds an O(N^0) correction. If ln Z_gas is the only O(N^0) term retained, the first-order coexistence shift is

delta_chi_c = 3*ln Z_gas(chi_HP)/(2*pi^2*N^2) > 0.

This is conditional, not the complete finite-N shift. Include black-hole one-loop determinants and all other O(N^0) terms before claiming a complete corrected transition temperature.

## 6. Required outputs

- SPECTRUM.csv / SPECTRUM.json: complete KK tower with exact degeneracies and source locators.
- SPEC.json: theory, spin structure, vacuum convention, spectrum coverage and truncation policy.
- RESULT.json: Z_gas, F, E, S, C_V over a declared chi grid.
- CHECKS.json: spectrum sum rules, bose/fermi signs, low-temperature limit, convergence, derivative checks and vacuum matching.
- REPORT.md: derivation, spectrum completeness argument, high-temperature domain and interpretation limits.

## 7. Required tests

A01 completeness: every field/tower in the cited IIB-on-S5 KK spectrum appears exactly once.
A02 degeneracies: reproduce representation dimensions and descendant multiplicities.
A03 thermal spin structure: fermionic modes use the ordinary antiperiodic thermal trace.
A04 vacuum: thermal gas excludes vacuum energy; add E_vac once only.
A05 low-T: ln Z_gas, E_gas, S_gas and C_V vanish as T->0.
A06 convergence: partial sums converge for each chi in the declared domain.
A07 polynomial growth: verify the large-energy density asymptotic and absence of a KK-gas Hagedorn pole.
A08 thermodynamic derivatives: E, S and C_V agree through independent derivative routes.
A09 HP matching: common-vacuum free energies reproduce the leading equality at chi_HP.
A10 correction: the O(N^-2) shift is reported only with all retained one-loop contributions explicitly listed.
A11 cutoff separation: stringy Hagedorn and gravitational collapse are not conflated.
A12 reproducibility: a clean rerun reproduces spectrum hashes and numerical tables.
A13 integer/half-integer grading: bosonic modes occupy integer global energies; fermionic modes occupy half-odd-integer energies under the ordinary thermal spin structure.
A14 low-level KRN match: compare the first KK levels, SO(6) representations, field spins, masses/conformal dimensions, and pure-gauge doubleton subtraction directly with KRN. The epsilon^8 asymptotic cannot detect low-level errors.
A15 asymptotic multiplicity: reproduce rho_1(epsilon)~epsilon^8 from the complete catalogue without fitting; distinguish fixed-level density from cumulative count.

## 8. Acceptance

A pass establishes the strong-coupling thermal-AdS supergravity gas at the declared approximation. It does not establish finite-lambda interpolation, the exact full string partition function, Lorentzian transition dynamics, a cosmological X-sector, or portal collision terms.
