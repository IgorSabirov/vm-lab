# R135: primary-source bytes as physical-stage inputs

`r135/donor_inputs.py` connects the PR #160 source readers to the executable
P1/P5/P6 package. It reads the cached **primary files**, verifies their exact
size and SHA-256 on every preparation, extracts the published numbers and
converts the selected preparation to MeV units. It does not use the saved audit
JSON as the source of a physical parameter.

The source URLs and release checksums remain in
[`donors/sources.json`](donors/sources.json). The output additionally records
the source-lock hash, every consumed source-file hash and the reader hashes.
An absent/corrupted cache entry is a failure in the default offline mode.
Downloading is possible only with the explicit `offline: false` choice and
still requires the pinned bytes to match.

## P1 input and scale alternatives

The P1 configuration can contain `donor_inputs` instead of separately supplied
`eos` and `scale`. Giving both forms is rejected. A complete thermal initial
surface remains required; the mass and entropy ratio of a literature point do
not specify neutrino distributions or all initial abundances.

```json
{
  "cache": "/tmp/r135-fresh-donors",
  "offline": true,
  "point_id": "XB-FMS-top-left",
  "scale_method": "r0",
  "entropy_covariance_policy": "diagonal_sensitivity",
  "pressure_anchor_uncertainty": {
    "sigma_over_Tc4": 0.0,
    "kind": "diagnostic_fixed_anchor",
    "source": "fixed for this code control; physical anchor uncertainty remains open"
  }
}
```

This example deliberately declares its two unresolved uncertainty choices. It
does not constitute a physical covariance determination. Alternatively, omit
`point_id` and supply a sourced `anchor` with `value`, `sigma`, `unit: MeV` and
`origin` for the scalar mass m0. A fixed FMS point and a second mass anchor
cannot coexist. The four masses and entropy ratios are extracted directly from
the [FMS figure 3 caption](https://arxiv.org/abs/1605.08048), keeping their
`external_model` origin. The SM entropy table is read in its original GeV
units; the calculated cold-boundary T_gamma is then converted to MeV.

Five dimensionless routes are kept separately:

- `r0`: [Francis et al.](https://arxiv.org/abs/1503.05652) r0 Tc divided by
  [Morningstar–Peardon](https://arxiv.org/abs/hep-lat/9901004) r0 m0.
- `string_tension`: the Tc/sqrt(sigma) and m0/sqrt(sigma) values quoted by
  [Giusti et al.](https://arxiv.org/abs/2502.03875).
- `flow_beta_6.222`, `flow_beta_6.135`, `flow_beta_6.117`: continuum Tc sqrt(t0)
  divided by the finite-a Wilson masses from the explicitly pure-gauge table
  of [Athenodorou et al.](https://arxiv.org/abs/2308.10054). These require
  `allow_finite_a_scale: true`; their quoted denominator errors contain only
  the measured mass error, not flow interpolation or continuum extrapolation.

These routes are sensitivity alternatives, not independent repetitions to be
averaged. Absolute and relative error contributions and the first-order range
under unknown correlations are retained. Their absolute scale remains a
parameter unless a model-X dimensional anchor is independently supplied.

## A stable EOS from measured entropy, with a common pressure zero

The [Giusti EOS](https://arxiv.org/abs/2501.10284) supplies marginal entropy
errors at 25 temperatures and the two one-sided entropy values at Tc. The
cold published fit has an unsuitable limiting derivative immediately below
Tc. The adapter therefore uses the measured entropy nodes directly, with
separate cold and hot intervals; it never differentiates a phase jump.

`EntropyTableEOS` implements `kind: entropy_integral_table`. Within each
interval entropy is linear, and pressure is its **exact integral** from the
common sourced anchor:

\[
p(T)=p(T_c)+\int_{T_c}^T s(T')\,dT',\quad
\rho(T)=T s(T)-p(T),\quad c_V=T\frac{ds}{dT},\quad
c_s^2=\frac{s}{T\,ds/dT}.
\]

Both phases share p(Tc)/Tc^4 = 0.01768 from the donor hot pressure fit.
The one-sided entropy values are 0.2928 and 1.471 in Tc^3 units. Their
difference gives L/Tc^4 = 1.1782; the separately quoted combined 1.175(10)
is preserved as a control from the same data, not a second independent datum.
The common pressure anchor cancels from the latent heat.

The stable domains are **0.8 Tc <= T <= Tc** and **Tc <= T <= 2.5 Tc**.
Entropy, heat capacity, energy density and causal sound speed are checked
inside the interpolation intervals. Heat capacity is one-sided at knots.
Pressure and density covariance use the exact integral/interpolation weights,
including optional pressure-anchor/entropy covariance. There is no
extrapolation or manufactured metastable continuation. The full joint
covariance and node order are retained so later uncertainty propagation can
preserve correlations between phases and the shared anchor.

`diagonal_sensitivity` uses the published marginal errors with explicitly zero
node covariances. `supplied_joint_covariance` requires a sourced joint matrix
whose diagonal reproduces those same published marginal errors. Neither
choice by itself validates the interpolation error or the pressure-anchor
error. The adapter therefore retains
`production_precision_validated: false` and `physical_input_status: PARTIAL`.

## P5 matched-interface control

`prepare()` returns the matched Ns=32, Nt=4 tadpole-action values from
[Beinlich–Karsch–Peikert](https://arxiv.org/abs/hep-lat/9608141): sigma/Tc^3 =
0.0125(17), L/Tc^4 = 1.40(9). The dimensional sigma and L and the correlation
sensitivity of K are computed from that same preparation. This finite-a L is
**not substituted** for the continuum EOS latent heat.

`thin_wall_control(prepared, config)` constructs a P5-compatible `thin_wall`
input only when `finite_a_diagnostic: true` and the supercooling domain are
explicit. It uses Delta p = L (1-T/Tc), requires a separately supplied
dimensional prefactor at each temperature, and retains
`physical_input_status: DIAGNOSTIC_ONLY`. The returned kernel does not supply
wall transport or a continuum metastable EOS. An absent prefactor stays open.

In P5, put this helper's configuration in `donor_thin_wall`, provide the
normal independent `wall` input, and bind the P1 `donor_inputs.json` artifact
under input name `donor_inputs`. A simultaneous `nucleation` definition is
rejected. P5 writes the usual numerical kernel and wall artifacts plus
`donor_thin_wall_control.json`; the stage evidence is **`DIAGNOSTIC`**, so it
cannot silently become a physical transition input. The optional
`gw_source.json` continues to be produced independently of this choice.

## P6: partial portal and number-changing coefficients

The prepared artifact also preserves the 12 source-table glueball states,
their JPC labels, spin multiplicities, and masses in MeV. P6 emits them as
`donor_relic_spectrum.json` when a donor helper is selected. These rounded mass
ratios carry neither a supplied covariance nor populations, reaction channels
or stability assignments. They are not inserted into `model.relics` as stable
particles merely because the missing widths are unknown.

`scalar_partonic_width(prepared, config)` reads the scalar matrix element and
operator normalization from [FMS portals](https://arxiv.org/abs/1710.06447):

\[
\Gamma(0^{++}\to gg)=K_{gg}\alpha_s^2\chi_3^2 m_0^9/M^8.
\]

The helper requires the model masses, bath temperatures, sourced process-energy
support and its omitted-tail budget, an explicit EFT hierarchy criterion,
running alpha_s table and a partonic validity domain. It checks m0/M, T_X/M,
T_gamma/M and E_max/M. The running table is interpolated in log(mu), without
extrapolation; every flavour change must occur at a declared matched threshold
knot. A scalar mass differing from the P1 preparation is rejected.

The output is always `PARTIAL_WIDTH_ONLY`, with
`usable_as_total_width: false`. At 1 GeV this expression is not promoted to a
complete hadronic width. Hadronic matching, other channels, C-odd states,
inverse reactions and cosmological energy deposition remain `OPEN_INPUT`.
The supplied matrix-element variation is recorded separately from the
uncomputed full uncertainty budget.

`nda_3to2(prepared, config)` returns the FMS low-momentum estimate

\[
\langle\sigma v^2\rangle=\frac{B}{(4\pi)^3}
 \left(\frac{4\pi}{3}\right)^6m_0^{-5}.
\]

B enters **linearly**, and the result has units MeV^-5. In a seconds-based
number equation it appears divided by hbar in MeV s. The isolated 3<->2
process conserves total species energy: its changing number must be solved
together with that energy, not with a prescribed temperature.

An explicit temperature domain and a sourced kinetic-equilibrium condition
are required. The latter compares momentum relaxation with both H and the
chemical evolution rate, with a declared separation margin above unity.
`NDA_SENSITIVITY` and `B_probability_measure: null` prevent interpreting a
B=0.3, 1, 3 scan as a probabilistic error distribution. This remains a
single-scalar MB approximation, not a full glueball reaction network.

### Executable P6 selection and downstream binding

P6 accepts `donor_scalar_portal` and/or `donor_3to2` in its configuration and
the same P1 `donor_inputs` artifact as an input. The ordinary `model` or
`collision_definition` remains required: the helpers do not assume a thermal
transfer history or declare a sector isolated on the caller's behalf. The
complete diagnostic configurations used for replay are saved in
[`P6_CONFIG.json`](donor_reference/control/P6_CONFIG.json); their explicitly
assigned physical coefficients are software controls.

| Selected calculation | Saved artifact | Stage interpretation |
| --- | --- | --- |
| `donor_scalar_portal` | `scalar_portal_partial_width.json` | `PARTIAL_WIDTH_ONLY`; stage evidence remains `OPEN_INPUT` |
| `donor_3to2` | `number_changing_model.json` | `NDA_SENSITIVITY`; conditional number-changing input |
| Either helper | `donor_physical_acceptance.json` | Records unresolved physical requirements and proves that the partial width was not inserted into a total or Q |

The partial gg result never changes `model.relics`, `decay_table.csv`, a
lifetime, branching fraction, or an energy-transfer moment. Selecting that
helper requests a partial calculation, and does not certify a complete
portal even if unrelated model channels are present. A complete independently
matched decay/transfer model uses the ordinary P6 interface and must carry
its own evidence. If both donor helpers are selected, the partial portal
keeps the combined stage `OPEN_INPUT`; a separately executed number-only P6
stage can provide the NDA coefficient to a conditional P7 calculation.

`number_changing_model.json` has schema `R135-FMS-NDA-3to2-v1`. The P7 binding
uses `coefficient_MeV_minus5`, `m0_MeV`, `T_X_range_MeV`,
`kinetic_equilibrium`, and `low_momentum_applicability`, with `mass_source`,
`source`, `donor_sha256`, and `prepared_input.sha256` preserving provenance.
It supplies a reaction coefficient and its declared approximation domain,
not an initial abundance or a temperature history. The receiving integrator
must reject a different scalar mass or an excursion outside this domain.

Downstream donor consumption also checks the P1 schema, the exact current
source-lock hash, the complete consumed-source inventory and reader hashes.
The normal pipeline additionally verifies the upstream receipt and actual
artifact hash. A changed reader or release requires P1 to be replayed;
downstream stages do not silently prepare another point or use stale output.

## Reproduction

From the software directory:

```sh
R135_DONOR_CACHE=/tmp/r135-fresh-donors python -m unittest discover \
  -s tests -p test_donor_inputs.py -v
python donor_reference/validate.py --cache /tmp/r135-fresh-donors \
  --out /tmp/r135-donor-stage-replay
```

The [saved control](donor_reference/control/VALIDATION.json) runs the actual
source-driven P1, checks the stable domains, reproduces all four cold
boundaries, then executes P5 and both P6 selections using that exact P1
artifact. It checks that the finite-a branch stays diagnostic and the partial
portal stays open, with an empty decay table in the isolated control. The
tests also reject corrupted source bytes and changed downstream provenance,
extrapolation, undocumented covariance, incompatible EFT scales and
inadequate kinetic relaxation.
No physical R135 production run or independently calibrated X point is added.
