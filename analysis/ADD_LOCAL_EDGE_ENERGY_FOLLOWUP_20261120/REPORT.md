# Follow-up: held-out local ADD energy test and physical blockers

Date: 20 November 2026. This report separates a finite combinatorial validation from the physical X/BH1/BBN gates.

## A. Five held-out matched pairs

The local functional family is unchanged:

```
e_i = (s_i, s_{i+1})                  # directed edge, b -> a
E(w) = sum_i eps[e_i] + sum_i eta[e_(i-1), e_i, e_(i+1)]
```

One fixed coefficient vector was selected deterministically from the motif tuple codes **before** the held-out pairs were selected:

- `eps(11)=-46, eps(12)=-9, eps(21)=-36, eps(22)=1`;
- `eta(1111)=-66, eta(1112)=-13, eta(1121)=93, eta(1122)=-65`;
- `eta(1211)=-11, eta(1212)=42, eta(1221)=-63, eta(1222)=-10`;
- `eta(2111)=99, eta(2112)=-59, eta(2121)=47, eta(2122)=100`;
- `eta(2211)=-57, eta(2212)=-4, eta(2221)=102, eta(2222)=-56`.

No coefficient was changed between pairs. The five pairs were selected from the finite family `w=h||(3-h)`, `h in {1,2}^12`, grouped by the complete directed pair-correlation vector. The pair selection was completed before evaluating E. The 10 words are disjoint from the R131/R132 dihedral orbits.

| Pair | A | B | E(A) | E(B) | ΔE |
|---:|---|---|---:|---:|---:|
| 1 | `111121212211222212121122` | `111211212111222122121222` | -527 | 106 | -633 |
| 2 | `111122112121222211221212` | `111212112111222121221222` | -527 | 106 | -633 |
| 3 | `111212122112222121211221` | `111222121221222111212112` | -527 | 106 | -633 |
| 4 | `111221121212222112212121` | `111222122121222111211212` | -527 | 106 | -633 |
| 5 | `112111222121221222111212` | `112121221122221212112211` | 106 | -527 | 633 |

For every pair, exact integer checks confirm:
- all-shift, all-label three-point correlation tables are equal;
- directed edge-count vectors are equal;
- four-vertex motif-count vectors differ;
- the fixed scalar E differs.

**Threshold: 5/5 pairs distinguish; requested threshold was 4/5.**

Important qualification: the five pairs all belong to **one** three-point-correlation class (96 members in the enumerated construction). They are five disjoint held-out comparisons, but not five independent correlation classes or independent physical datasets. Therefore this validates the expressive power of this frozen local ansatz on held-out words; it does not statistically exclude chance or establish a physical law.

The coefficient vector is arbitrary and dimensionless. It was not calibrated to X and is not the missing physical derivation of `eps` and `eta`.

## B. Why a physical H_X, Z, F, S, C_R and tau_X are not yet determined

The local functional defines only a potential energy on static binary cyclic words. It does not define:

1. a physical Hilbert/state space or phase-space measure for X;
2. conjugate momenta, inertia/mass, or a quantum hopping operator;
3. a kinetic generator or coupling to a bath;
4. transition rates for the ADD events and detailed balance;
5. a physical energy unit converting the arbitrary integer coefficients to eV/MeV;
6. the map from graph length to physical radius/volume and cosmological time.

A formal extension such as `H_X = E(w) + sum_i p_i^2/(2m_X)` is possible, but `m_X` and the momentum variables are additional assumptions. Multiplying every kinetic rate by an arbitrary constant rescales `tau_X` without changing the static E table. Thus `tau_X/H^{-1}` is unidentifiable from the current data.

For a specified finite-range classical model, a transfer matrix can define `Z=Tr(T^L)`, then `F=-T ln Z`, `S=-dF/dT` and `C_R=-T d^2F/dT^2`. But the present coefficient vector is arbitrary, the functional is currently specified only on the binary 1/2 subspace, and the ADD update also creates/uses state 3. There is no closed physical ensemble or temperature scale yet. Any numerical thermodynamic table would therefore be a result for an invented toy model, not for the physical X in BH1.

**B verdict: NOT COMPUTABLE AS PHYSICS.** A formal toy partition function is possible after explicitly choosing an ensemble and kinetic extension; it cannot produce a physical relaxation time without a microscopic rate law and dimensional calibration.

## C. Why the BBN budget cannot yet be tested against this E_X

The benchmark `Delta rho = 0.0445181 T_gamma^4`, with 59.12% to photons and 40.88% to free-streaming radiation, is a required cosmological transfer. The pure-SU(3) latent-heat values `L/T_c^4=1.025(21)(27)` and `1.175(10)` are external equation-of-state data for a specific four-dimensional gauge theory.

The current local E has no physical units, volume density, equation of state, transition latent heat, hidden temperature ratio, conversion efficiency, decay/portal rates, or branching fractions. It therefore cannot be compared numerically with `0.0445181 T_gamma^4`. Assigning a scale to E or borrowing the SU(3) latent heat as if it were derived from this ADD functional would be a fit/identification assumption, not a prediction.

**C verdict: NOT COMPUTABLE; no BBN run authorized by this test.** The SU(3) threshold remains a conditional external benchmark, not the energy of the derived ADD sector.

## Overall status

- Local combinatorial separability on five held-out matched pairs: **PASS (5/5)**.
- Physical origin of coefficients from X: **OPEN**.
- Closed Hamiltonian and thermodynamic ensemble: **OPEN**.
- Relaxation time versus Hubble time: **OPEN / UNIDENTIFIABLE**.
- Energy transfer and BBN budget closure: **OPEN**.

The contact-order branch should **not** be closed: the local ansatz survives this finite held-out test. But the physical X/BH1 gate has **not** passed. Next required input is a microscopic definition of X that fixes the local coefficients, its state space and kinetic transition rates independently of these word tests.
