# Nonthermal distributions and electron-neutrino weak rates

## What this delivery computes

`r135/kinetics.py` evolves homogeneous, isotropic particle occupations on
comoving momentum cells, including Fermi blocking, Bose stimulation or classical
statistics. The collision operators are supplied inputs with an explicit source.
The module computes the energy and pressure of the **evolved distribution**, and
uses the energy moment of the same collision term as the source for its recipient
bath. `integrate_kinetic_bath` is an executable joint distribution/bath/expansion
solver. `kinetic_rhs` and `MomentumGrid` expose the same calculation to P7.

`r135/neutrino_rates.py` integrates all six neutron/proton charged-current
processes for independent arbitrary electron-neutrino and antineutrino
occupations. These are **Born rates with infinitely heavy nucleons**, normalized
to a specified free-neutron lifetime. The result is a calculated time-indexed
weak table for P8, not a thermal temperature fitted to a distorted spectrum.
Every result explicitly carries `production_precision_validated: false`.

These numerical components remove two specific software restrictions: a
nonthermal species no longer has to be replaced by a temperature and a
distorted electron-neutrino spectrum no longer has to be replaced by thermal
weak rates. They do not supply model-X collision amplitudes or the missing
precision corrections for arbitrary spectra.

## Sources, pins and licensing

The exact references, donor commits, relevant file SHA-256 values and licenses
are in [`neutrino_reference/sources.json`](neutrino_reference/sources.json).

* Pitrou, Coc, Uzan and Vangioni, *Physics Reports* **754** (2018),
  [DOI 10.1016/j.physrep.2018.04.005](https://doi.org/10.1016/j.physrep.2018.04.005),
  [arXiv:1801.08023v3](https://arxiv.org/html/1801.08023v3): thermodynamic moments,
  six crossed weak reactions, Born integrals and lifetime normalization,
  especially Sections II.1, III.1–III.3 and Eqs. 67–91.
* Mangano et al., *Nuclear Physics B* **729** (2005) 221–234,
  [DOI 10.1016/j.nuclphysb.2005.09.041](https://doi.org/10.1016/j.nuclphysb.2005.09.041),
  [arXiv:hep-ph/0506164v1](https://arxiv.org/html/hep-ph/0506164v1): homogeneous
  transport, statistical factors, energy continuity and comoving momentum,
  Eqs. 4 and 7–9. The paper's full flavour-matrix calculation is **not**
  reproduced by the supplied-kernel solver.
* [LINX](https://github.com/cgiovanetti/LINX) commit
  `bfba07c77a5fcba1cc772d42f2d9e9be8a542df8`, MIT, supplies the independent native
  Born comparison and selected correction comparison.
* [PRIMAT](https://github.com/CyrilPitrou/primat) commit
  `6f7e5680614fb119d65a6c9c65a292240b27c61e`, GPL-3.0-or-later, was inspected for
  its rate conventions, neutron normalization and the distinction between Born
  and corrected nonthermal integrals. Its correction routines are not copied
  into these modules.

The new algorithms are original implementations of the stated equations; no
upstream source or paper text is vendored. The existing backend source loader
already supplies the pinned native donor. No access token, private data, network
download or dependency installation is hidden in the validation script.

## 1. Momentum-resolved evolution and energy exchange

### State and moments

With physical momentum `p` and dimensionless scale factor `a`, define `q=a p`.
For an isotropic distribution,

\[
 (\partial_t-Hp\,\partial_p)f=C[f]
 \quad\Longrightarrow\quad
 \left.\frac{df}{dt}\right|_q=C[f].
\]

The numerical state is a cell-constant occupation `f_i` between supplied edges
`q_i` and `q_(i+1)`. The number weight is exactly

\[
 w_i=\frac{g}{6\pi^2}(q_{i+1}^3-q_i^3),\qquad
 n=a^{-3}\sum_i w_i f_i.
\]

The energy and pressure use the same cells:

\[
 \rho=\frac{g}{2\pi^2a^3}\sum_i f_i
  \int_{q_i}^{q_{i+1}}q^2\sqrt{m^2+q^2/a^2}\,dq,
\]

\[
 P=\frac{g}{6\pi^2a^3}\sum_i f_i
  \int_{q_i}^{q_{i+1}}\frac{q^4/a^2}{\sqrt{m^2+q^2/a^2}}\,dq.
\]

Massless moments are analytic. Massive moments use a declared Gauss-Legendre
order, default 24 per cell. A single massless neutrino helicity uses `g=1`;
antineutrinos have a separate state. The massless result has `P=rho/3` exactly.
Collisionless cells retain their occupations, while `n a^3` and `rho a^4` are
constant for massless particles. The massive implementation obeys
`d rho/d ln a = -3(rho+P)` with the same moment quadrature.

For a computed derivative `C_i` the source is

\[
 Q=\frac{g}{2\pi^2a^3}\sum_i C_i
  \int_{q_i}^{q_{i+1}}q^2\sqrt{m^2+q^2/a^2}\,dq,
 \qquad
 \dot\rho+3H(\rho+P)=Q.
\]

`Q` is in `MeV^4/s`; the number source is in `MeV^3/s`. No extra conversion
by `hbar` belongs here because the input collision rates already use seconds.
The recipient bath must receive **the same `-Q`**, including negative `Q` for
inverse transfer. A kinetic species replacing a thermal sector must replace
that sector's density and pressure in the expansion equation as well.

### Implemented collision operators

Let `eta=-1,+1,0` for fermions, bosons and classical particles, respectively.

| Operator | Computed derivative | Required physical input |
|---|---|---|
| `EmissionAbsorption` | `C_i=j_i(1+eta*f_i)-kappa_i*f_i` | Both `j_i` and `kappa_i` in `s^-1`, with their source and domain |
| `ConservativeScattering` | Pairwise transfers `W_ij*w_j*f_j*(1+eta*f_i)`, minus each inverse, divided by `w_i` | Nonnegative inter-cell transition matrix `W_ij` in `s^-1`, with its source and domain |
| No operators | `C_i=0` | Explicit collisionless preparation |

Coefficients may be arrays or callables `coefficient(time_s,a,T_bath_MeV)`.
This permits actual bath-temperature feedback in an ODE solve. The test helper
`detailed_balance_transition` constructs a reversible discrete transition
matrix from a **supplied symmetric conductance**. It verifies the numerics;
it does not calculate a portal amplitude. The pairwise form conserves particle
number at roundoff independently of the magnitude of energy exchange.

`MomentumGrid.equilibrium` returns FD/BE/MB occupation at the cell mean energy.
This is the exact fixed point of the corresponding discrete reversible kernel,
not a claim that point sampling equals the continuum cell average. Grid and
support refinement remain necessary. Bose chemical potentials above the rest
mass are rejected. Bose occupations may exceed one. The solver has **no delta
function condensate mode** and does not claim to follow condensation.

### Standalone joint integration and P7 API

```python
grid = MomentumGrid(q_edges_MeV, mass_MeV=0., degeneracy=1.,
                    statistics="fermion")
operator = EmissionAbsorption(grid, emission_s_inv, absorption_s_inv,
                              source="explicit physical or diagnostic source")
df_dt, moments = kinetic_rhs(grid, [operator], time_s, f, a, bath_T_MeV)
Q_MeV4_s = moments["energy_MeV4_s"]
density = grid.moments(f, a)  # rho_MeV4, pressure_MeV4, number_MeV3
```

The independently usable `integrate_kinetic_bath` integrates `(a,rho_b,f_i)`
together with `rho_b=c*T_b^4`, `P_b=rho_b/3` and
`dot rho_b=-4H*rho_b-Q`. It also integrates the expansion work, so its audit is

\[
 a^3(\rho_b+\rho)+\int 3Ha^3(P_b+P)\,dt
  =a_0^3(\rho_{b0}+\rho_0).
\]

The supplied `H` may be a constant or a function of time, scale factor and total
density. This radiation-bath helper is not substituted for an SM EOS including
electron annihilation. A general P7 EOS uses the lower-level moments/RHS.

The actual P7 adapter is `r135/kinetic_history.py`. Its JSON contract is shown
in [`examples/nonthermal_control.json`](examples/nonthermal_control.json).
Each `kinetic_species` declares its sector (`nu`, `free`, or `relic`), statistics,
degeneracy, mass, comoving edges, initial occupations and sourced operator.
Resolved sectors replace their thermal energy/pressure in the common P7 state.
`thermal_closure_source` still declares applicability for the remaining thermal
bulk and reservoirs; it must not describe the resolved neutrinos as thermal.
The `nu` sector must explicitly include `nu_e` and `antinu_e`; the example also
retains all four mu/tau helicities. Oscillations are absent. A resolved relic
must declare `excluded_from_phase_eos: true`; duplicate MB relics are rejected.

Besides fixed arrays, a JSON coefficient can be a sourced table:

```json
{"kind":"bath_temperature_table", "source":"identified physical calculation",
 "T_MeV":[0.1,1.0], "values_s_inv":[[0.001,0.002],[0.01,0.02]]}
```

These illustrative numbers are not physical input for X. The first array axis
is bath temperature; subsequent axes are momentum cells (or a transition
matrix). P7 evaluates the coefficient at the **current** bath temperature and
rejects extrapolation. The reciprocal source changes that same bath's energy.
Initial thermal neutrino data cannot coexist with resolved neutrino cells.
The exported `T_nu_energy_equivalent_MeV` is diagnostic, while weak integrals
read the original occupations at physical edges `q/a(t)`.

The solver fails if a material negative occupation or fermionic occupation
above one survives integration. It never clips an invalid spectrum into a
valid one. Small numerical bound violations are exposed in
`max_occupation_bound_violation`, and the caller must refine them before using
a strict weak-spectrum contract. Implicit ODE trial stages may briefly leave
the occupation domain; moments remain linear at those trial stages.

## 2. Arbitrary-spectrum neutron/proton rates

### Six processes, thresholds and normalization

Use an electron/positron thermal bath with opposite chemical potentials,
`f_e-(E)=1/[exp((E-mu_e)/T_gamma)+1]` and
`f_e+(E)=1/[exp((E+mu_e)/T_gamma)+1]`. Electron-neutrino and antineutrino
occupations are independent inputs. Nucleons are dilute and at rest; their
mass gap `Delta=m_n-m_p` is retained. With

\[
 K(E,E_\nu)=E\sqrt{E^2-m_e^2}\,E_\nu^2,
 \quad
 A=\left[\tau_n\int_{m_e}^{\Delta}
  E\sqrt{E^2-m_e^2}(\Delta-E)^2dE\right]^{-1},
\]

each rate is `A * integral dE K * statistical factor`:

| Process | Electron energy domain | Neutrino energy | Statistical factor |
|---|---|---|---|
| `n + nu -> p + e-` | `[Delta,infinity)` | `E-Delta` | `f_nu*(1-f_e-)` |
| `p + e- -> n + nu` | `[Delta,infinity)` | `E-Delta` | `f_e-*(1-f_nu)` |
| `n + e+ -> p + antinu` | `[m_e,infinity)` | `E+Delta` | `f_e+*(1-f_antinu)` |
| `p + antinu -> n + e+` | `[m_e,infinity)` | `E+Delta` | `f_antinu*(1-f_e+)` |
| `n -> p + e- + antinu` | `[m_e,Delta]` | `Delta-E` | `(1-f_e-)*(1-f_antinu)` |
| `p + e- + antinu -> n` | `[m_e,Delta]` | `Delta-E` | `f_e-*f_antinu` |

Rates are in `s^-1` because the normalization uses the declared neutron
lifetime in seconds. The default `879.4 s` and reference masses match the
existing pinned LINX constants; all three quantities can be passed explicitly.
This is not a new inference of the neutron lifetime or an X calibration.

At zero bath temperature and zero occupations the only remaining channel is
free neutron decay, exactly `1/tau_n`. At a shared temperature and opposite
neutrino chemical potentials each inverse pair satisfies

\[
 \frac{\lambda_{p\to n}}{\lambda_{n\to p}}
  =\exp[-(\Delta-\mu_e+\mu_\nu)/T].
\]

### Spectrum representation and numerical error

* `ThermalSpectrum(T_MeV,mu_MeV)` is an exact FD function integrated to infinity.
* `TabulatedSpectrum(energy_MeV,occupation,...)` is piecewise linear. A grid
  beginning above zero requires an explicit `low_energy="constant"` or
  `low_energy="zero"` policy.
  A finite tail requires `tail="zero"` and a final zero occupation.
* `BinnedSpectrum(energy_edges_MeV,occupation)` is piecewise constant with edges
  beginning at zero and zero support beyond the final edge. It consumes
  `MomentumGrid.massless_spectrum(f,a)` without refitting or losing the
  distribution's energy moment.

Quadrature splits at every spectral breakpoint and every kinematic threshold.
Reported errors estimate quadrature of the supplied representation. They do
**not** include momentum interpolation, omitted physical tails, model input
uncertainty or the omitted weak corrections. Those are separate convergence
and physics requirements. No number inferred from a thermal energy density can
replace this spectral convergence test.

`weak_rates_from_history` consumes `f_nu_e` and `f_antinu_e` time slices and
returns the existing P8 names `lambda_n_to_p_s_inv`, `lambda_p_to_n_s_inv`,
`time_s`, `unit` and `source`. For binned spectra, `energy_edges_MeV` may be
fixed or time dependent; kinetic physical edges are `q_edges/a(t)`. The output
is bound by `neutrino_spectra_sha256` to the complete actual input spectra.
Reheating and two times with the same photon temperature retain their distinct
spectra and rates; the routine never sorts the history by temperature.

## 3. Executed checks and measured limits

Development tests, requiring only NumPy/SciPy:

```sh
python -m unittest discover -s tests -p 'test_neutrino_rates.py' -v
python -m unittest discover -s tests -p 'test_kinetics.py' -v
```

The tests cover free streaming, massive energy/pressure continuity, source
normalization, all three statistics, number conservation, inverse reactions,
FD/BE/MB discrete equilibrium, finite-bath backreaction, all six weak channels,
thresholds, full Pauli blocking, chemical detailed balance, momentum refinement
and time/spectral provenance. They are numerical controls, not a physical-X run.

Two diagnostic spectra in `test_same_energy_spectra_are_not_interchangeable`
have exactly the same massless energy density, `0.4275279007 MeV^4`, but at the
same photon temperature their `n->p` rates differ by **1.8457%** and `p->n` by
**3.0639%**. This is a direct control against replacing all spectral effects
with a temperature or `Delta N_eff`.

In the finite-bath control, an explicitly diagnostic reversible kernel heats
initially empty particle cells. The bath cools from `1` to `0.91102438 MeV`;
the total-energy relative residual is about `7e-16`. Holding its kernel at the
initial temperature changes the computed distribution. Energy conservation
does not validate that kernel as a physical X interaction.

### Independent native Born comparison

Use the existing locked LINX environment and source checkout:

```sh
python neutrino_reference/validate_native_weak.py \
  --linx-source /path/to/pinned/LINX \
  --output /path/to/native_born_reference.json
```

The script verifies the donor commit and source hashes before importing it.
[`native_born_reference.json`](neutrino_reference/native_born_reference.json)
records the executed comparison, constants and dependency versions. The maximum
relative difference from the independent LINX 1000-point Born quadrature is
**2.47795e-5** over shared temperatures `0.3`, `1` and `3 MeV`.

This agreement validates the common approximation. It does not validate its
physical completeness. Enabling LINX's Coulomb/radiative, finite-mass and
weak-magnetism corrections, while deliberately leaving its thermal correction
tables off, changes the normalized rates by:

| `T_gamma=T_nu`, MeV | Corrected/Born minus one, `n->p` | Corrected/Born minus one, `p->n` |
|---|---:|---:|
| 0.3 | -2.3702% | -2.1673% |
| 1 | -3.8360% | -3.6336% |
| 3 | -6.3793% | -6.1752% |

The table isolates a set of omitted corrections in these thermal controls.
It is **not** an uncertainty bound for arbitrary nonthermal spectra, and it
does not include finite-temperature radiative corrections. Applying an
arbitrary constant correction to new spectra would not close that gap.

## 4. What remains open

1. **Precision weak rates for arbitrary spectra.** Finite nucleon mass/recoil,
   weak magnetism, Coulomb and zero-/finite-temperature radiative terms, thermal
   QED dispersion, and their consistent lifetime normalization are not included
   in the new arbitrary-spectrum module. Native precision methods remain
   available only within their registered input domains. The measured percent
   differences above prevent treating the new Born path as automatically ready
   for a high-precision abundance likelihood.
2. **Physical X kernels.** The solver requires emission, absorption,
   scattering, decay and inverse-process coefficients derived from the chosen
   amplitudes and physical preparation. A cited source string alone does not
   establish their physical validity. The generic operators do not synthesize
   missing amplitudes. Full nonlinear multi-species `2<->2`/`3<->2` collision
   tensors must be connected when the chosen model needs them.
3. **Flavour quantum kinetics.** Off-diagonal neutrino density matrices,
   oscillations, neutrino self-potentials and the full SM decoupling collision
   operator are not solved here. The input `f_nu_e` and `f_antinu_e` must be
   generated by a justified model or imported from such a solver.
4. **Other physical regimes.** Anisotropies, spatial transport near a wall,
   Bose condensates and mass-varying dispersion relations are not represented
   by fixed-mass homogeneous cells. Nucleons in the weak module are static and
   dilute; a high-energy input spectrum requires a separately established
   validity assessment, not just successful numerical integration.
5. **Production convergence.** The chosen model must pass momentum-support,
   grid, quadrature and time refinement, including its actual weak rates and
   downstream abundances. These controls do not establish a full physical
   R135 runtime or memory budget.
