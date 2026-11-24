# Coupled GW channel: executable scope and remaining physics

`r135/gravitationalwaves.py` couples a supplied, time-resolved GW source to the
**actual P7 energy history**. The same saved P7 history feeds BBN and the GW
response. The new coupling is tested numerically; it is not a calculation of a
GW production efficiency for cosmological X. All 52 frozen P0 point/path rows
remain `OPEN_INPUT` until their own physical source and subsequent history are
provided. The four published SU(3) preparations do not supply these inputs.

## 1. State, units and reciprocal energy transfer

The independent frequency coordinate is **cyclic** comoving frequency
`q = a*f`, in Hz, using exactly P7's arbitrary scale-factor normalization.
Frequency-cell edges are fixed in `q`. Within cell `i`, the state `g_i` and
supplied source `p_i(t)` mean

\[
g_i=\frac{d\rho_{\rm GW}}{d\ln q}\quad[\mathrm{MeV}^4],\qquad
p_i=\frac{dQ_{\rm GW}}{d\ln q}\quad[\mathrm{MeV}^4/\mathrm{s}].
\]

The implementation evolves

\[
\dot g_i+4H g_i=p_i(t),\qquad
\rho_{\rm GW}=\sum_i g_i\ln(q_{i+1}/q_i),\qquad
Q_{\rm GW}=\sum_i p_i\ln(q_{i+1}/q_i).
\]

P7 adds this density and `rho_GW/3` to the free sector, adds `Q_GW` to its
source, and subtracts the same source from X. The combined density contributes
to the Friedmann rate and both existing comoving energy ledgers. This changes
the finite X reservoir, its temperature, wall conditions and phase evolution.
Any independently resolved free-particle distribution remains present. The GW
state does not replace it or advance a second thermal copy of the same energy.

`GWSource(definition, offset=kinetic.size)` exposes `size`, `slice`,
`time_knots_s`, `initialize`, `moments`, `rhs` and `validate_accepted`.
P7 inserts every source knot into both integration boundaries and saved output.
Negative accepted cell densities are rejected; the output is not clipped to
make a failed solve appear positive. `GWSource(None, ...)` adds no state and
does not assert a zero physical prediction.

The source is currently **prescribed spectral power as a function of physical
time**, with optional five-corner multipliers. Its energy backreaction is
integrated. A self-consistent plasma/tensor source that recomputes its power
from the changing fluid stresses is not implemented by this contract.

## 2. Required source definition and applicability

P5 `config.gw_source` is frozen into `gw_source.json`. P7 can consume this
artifact as its `gw_source` input, checking its SHA-256 and point/model/path.
The source must declare:

| Field | Meaning |
|---|---|
| `kind = comoving_frequency_power` | Supported coupled representation |
| `source` | Origin of the physical or explicitly diagnostic power law |
| `support_source`, `uncertainty_source` | Justification of support and uncertainty treatment |
| `scale_factor_convention` | Exact convention for P7 `a` and `q=a*f` |
| `q_frequency_edges_Hz` | Positive, strictly ordered cell edges |
| `time_s`, `power_MeV4_s_per_logq` | Ordered times and nonnegative time-by-cell table |
| `zero_outside_time_support = true` | Explicit compact time support |
| `omitted_frequency_energy_fraction_bound` | Declared bound on unrepresented frequency energy |
| `applicability` | Sourced isotropic, subhorizon, freely propagating regime and maximum allowed density fraction |

The first and last power rows must be zero, making the piecewise-linear source
continuous at the boundary of its compact support. Nonzero initial cell
densities require a separate `initial_spectrum_source`. All five source
multiplier keys must be present if multipliers are supplied.

For every occupied or emitting cell the lower frequency edge must satisfy
`2*pi*q_low/a > H`. A superhorizon cell returns `OPEN_INPUT`: the short-wave
radiation equation is then insufficient. The declared maximum GW fraction is
also enforced throughout P7 and the late propagation. These are checks of a
supplied applicability statement, not a derivation of the source's tensor
perturbation theory.

The phase-transition source discussion and acoustic fits motivating the
separate legacy end-spectrum control are in
[Caprini et al., arXiv:1910.13125](https://arxiv.org/abs/1910.13125).
That paper does not determine R135's bulk kinetic fraction, length scale,
source duration or conversion efficiency. The code does not assign them from
latent heat. `gw/response.py` retains the end-of-emission tabulated/acoustic
interface; it is not silently converted into a time-dependent P7 source.

## 3. Propagation and BBN use the same history

The response policy must supply a sourced late `H(a)` continuation beginning
at the **actual final P7 scale factor and Hubble rate**. Its supported
interpolation is `piecewise_linear_H_of_a`, and free propagation must be stated
explicitly. Its final `a` defines today's scale factor in the P7 convention.
A photon temperature alone cannot determine this continuation when later
entropy transfer or relic decay is possible.

The present spectrum follows from the final saved cell density:

\[
f_{0,i}=q_i/a_0,\qquad
\Omega_{0,i}=g_i(t_f)(a_f/a_0)^4/\rho_{c,0},\qquad
\rho_{c,0}=\frac{3(\hbar H_0)^2}{8\pi G}.
\]

The transferred spectrum remains constant per logarithmic frequency inside
each cell. The horizon test covers the entire late interpolation, including
interior maxima of `a*H`; endpoint checks alone can miss a crossing. The GW
fraction is checked on every segment as well.

Each requested BBN epoch must identify one unique retained P7 time and give
the source of its physical selection. The budget integrates the actual cell
energy at that time with its horizon cutoff. It never transports a spectrum
from a later emission epoch backward into a universe that had not generated
it yet. GW energy is **already included in P7's Hubble rate** and is not added
again as an extra BBN `DeltaNeff` source.

P8 retains the BBN history if its CMB mapping is still open. A GW background
does not automatically authorize an ordinary adiabatic scalar `N_ur`
replacement in CLASS. Native scalar mapping requires a separately supplied,
history-bound applicability artifact. Its existence is evidence for physical
review, not an independent numerical solution of the perturbation problem.
P10 does not promote such a statement to completed cosmological physics.

## 4. Detector projection and inference limits

P9 accepts its actual `channel_history` input and verifies its **file SHA-256**
against `bbn_inputs.source_P7_file_sha256`. Every one of the five corners also
has a canonical history digest, source digest, response-policy digest and
point/model/path identity. Missing sources or late histories produce explicit
per-corner `OPEN_INPUT` records without an invented zero spectrum.

When `donor_cache` is supplied, the three detector donors are checked against
their pinned bytes and SHA-256 on every use:

- LVK O4a Hanford–Livingston cross-correlation bins, errors and mask from the
  [official release](https://dcc.ligo.org/LIGO-G2502630/public).
- The pinned NANOGrav 15-year Fourier-bin/KDE archive in
  [donors/sources.json](donors/sources.json).
- The pinned O1–O4c1 publication, whose power-law upper limits are reported as
  contextual results and are **not applied to an arbitrary R135 shape**.

The actual numerical products are a diagonal Gaussian LVK
`Delta logL` relative to zero for fixed foreground/calibration treatment, and
NANOGrav Fourier-bin characteristic-strain/RMS projections. The latter are
not the full Hellings–Downs likelihood. Shared-data treatment, astrophysical
populations, priors and detector systematics remain explicit open tasks.
No joint BBN+CMB+PTA+LVK posterior is claimed by these projections.

## 5. Independent audit and coverage

`audit_history` reconstructs cell moments and source powers and independently
integrates `a^4*p_i` over the saved trajectory. The P10 P7 audit checks this
against the raw CSV trajectory and the sector energy balances. If kinetic
free particles coexist with GW, both contributions enter its independently
reconstructed free density and pressure exactly once.

`audit_response` does **not call the producing `response_from_p7` function**.
It rebuilds today's cell frequencies and densities, the logarithmic integral,
and every BBN budget with scalar sums from raw P7 cells and physical constants.
With an offline pinned cache it also repeats the detector projections. Missing
detector replay is reported explicitly rather than trusting a saved number.

`gw_channel_status.json` accounts for every point/path in the supplied frozen
P0 register, even when the selected claim matrix is a subset. The published
register has 52 such rows. Missing GW physics keeps the affected cosmological
claim partial. An independent `graph_as_XB_marker` measurement or a clearly
reduced software fixture does not acquire an unrelated GW requirement.
Only the existing independently checked necessary-condition counterexample,
bound to its exact XA law and preparation, can excuse its declared downstream
GW work. A text-only inapplicability claim cannot close a physical branch.

## 6. Reproducible numerical control

The archived run is [gw/integrated_reference/VALIDATION.json](gw/integrated_reference/VALIDATION.json).
It contains three actual P7 solves: source on, a tighter source-on solve, and
zero source with the same frequency cells and source knots. Their primary
inputs, histories, balances, spectrum, zero-source response and independent
audit are saved beside the report. This is an assigned diagnostic source,
not one of the 52 P0 physical candidate histories.

The saved control uses `exchange_during_transition`, matching the actually
executed P7 configuration and the identity embedded in every archived history.
Its tighter solve halves the maximum time step as well as tightening the
tolerance; the increase in actual RHS evaluations demonstrates that the
internal integration was refined.

| Actual solve | Relative tolerance | Maximum step in `H0^-1` | RHS evaluations |
|---|---:|---:|---:|
| Source on | `1e-9` | 0.025 | 6,161 |
| Source on, refined | `2e-10` | 0.0125 | 12,146 |
| Zero source | `1e-9` | 0.025 | 6,161 |

The final source-bound run took **18.6318 s** and reached **79,604 KiB
(77.74 MiB)** peak resident memory in its recorded environment. Its largest
relative change in the GW density cells under refinement was
`1.70824e-11`. Independent output-grid integration of `a^4*Q_GW` agreed with
the evolved GW energy change to `2.01207e-5` relative error. Turning on the
source changed the maximum phase-fraction difference by `2.05089e-6` and the
X temperature by `1.27367e-5 MeV`, so the test exercises finite-reservoir
backreaction as well as spectral transport. It used **30 PTA Fourier bins**
and **49,993 unmasked LVK bins**. All **52/52 physical-matrix GW rows remained
`OPEN_INPUT`**; numerical control data did not close a physical candidate.

To repeat it from this software directory, select a new output directory:

```bash
python gw/validate_integrated.py --out /tmp/r135-gw-replay --cache /path/to/pinned-donor-cache --offline
python -m unittest discover -s tests -p 'test_gravitationalwaves.py' -v
python -m unittest discover -s gw -p 'test_response.py' -v
```

The report records source hashes before and after execution, frozen data
hashes, dependency versions, peak resident memory and elapsed time. It refuses
to certify a run if its code or frozen inputs changed while it was executing.
Its resource measurements concern this small three-solve control; they do not
estimate the cost of a full physical source calculation, tensor simulation,
ensemble scan or observational posterior.

The regression tests cover finite-reservoir energy transfer, free redshift,
additive resolved-particle/GW density, generation timing, late horizon and
density-domain failures, corrupt cells, changed point/corner identities,
freshly rehashed corrupt transfers, 52-path coverage, and independence of
marker/reduced validation claims.

## Remaining inputs and development

Physical completion still requires the X-specific time/frequency source and
its uncertainty, a justified source-support error budget, the full late
thermal/expansion history, and applicable perturbation equations. Feedback
of the evolving fluid stress into the GW power itself requires a physical
source solver. Non-geometric-optics tensor evolution and damping are outside
this implementation. Detector projections require the full statistical
models above before they can yield an observational exclusion. These open
requirements appear in machine-readable responses and audits as well as here.
