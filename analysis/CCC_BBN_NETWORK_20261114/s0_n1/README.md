# S0-N1 — preregistered numerical-convergence study

**State:** DESIGN_FROZEN / NOT_EXECUTED  
**Scientific acceptance:** false  
**Parent S0:** [PR #47](https://github.com/IgorSabirov/vm-lab/pull/47)  
**Upstream:** PRIMAT 0.3.3, commit \`6f7e5680614fb119d65a6c9c65a292240b27c61e\`

S0-N1 asks a narrower question than a physical validation:

> How much do the full-network PRIMAT S0 observables and abundance trajectories move when the three numerical-resolution controls are refined independently, and does their joint refinement remain within a preregistered numerical budget?

This is not a parameter-uncertainty analysis, an independent-solver comparison, or a test of CCC+TL. It does not vary physical inputs or reaction-rate central values. It tests numerical stability of the already completed standard-BBN calculation under the pinned PRIMAT implementation.

## 1. Why this is not another COLD/WARM pair

The S0 COLD/WARM comparison established bitwise repeatability for the same executable, environment, input data and numerical settings. It did not estimate discretization or integration error.

The three controls have distinct roles:

| Control | Baseline | What it controls | What it does not mean |
|---|---:|---|---|
| \`numerical_precision\` | \`1e-10\` | Relative tolerance supplied to the era ODE solvers | It is not the effective LT rtol by itself |
| \`rate_grid_npts\` | \`4000\` | Master \(T_9\) grid onto which nuclear reaction-rate tables are resampled | It is not the number of ODE steps |
| \`sampling_temperature_per_decade\` | \`2000\` | Background temperature-grid density used for the \(a(T)\), \(t(T)\), and neutrino-temperature interpolation | It is not an output sampling count |

At the pinned Python backend, the actual relative tolerances are:

| Era | Solver | Effective rtol at baseline | Absolute tolerance |
|---|---|---:|---:|
| HT | LSODA | \(1\times10^{-10}\) | \(1\times10^{-10}\) |
| MT | BDF | \(1\times10^{-10}\) | \(1\times10^{-15}\) |
| LT | BDF | \(1\times10^{-9}\) | \(1\times10^{-26}\) |

For a changed \`numerical_precision=p\`, HT and MT use \`rtol=p\`; LT uses \`rtol=10p\`. Absolute tolerances remain fixed in this study and must be recorded explicitly in every run manifest. Thus the precision sweep estimates sensitivity to the configured relative tolerance at the pinned absolute-tolerance floors. If it plateaus in a way suggesting an absolute-tolerance floor, S0-N1 must report that limitation and propose a separately preregistered atol sweep; it must not claim that this sweep has tested every solver error control.

The two grid controls are independent error sources. The pinned upstream performance notes report second-order convergence for both grids, but their quantitative measurements were made on the small network. Those numbers motivate the refinement design; they are not P2 predictions or acceptance evidence. See the [pinned upstream performance document](https://github.com/CyrilPitrou/PRIMAT/blob/6f7e5680614fb119d65a6c9c65a292240b27c61e/docs/performance.md).

## 2. Frozen run matrix

R0 is the existing P2 COLD result and is reused as the baseline. It is not rerun. Each of R1–R8 is one full three-era solve; the existing bitwise COLD/WARM test makes another identical warm solve unnecessary for this question.

| ID | \`numerical_precision\` | \`rate_grid_npts\` | \`sampling_temperature_per_decade\` | Purpose |
|---|---:|---:|---:|---|
| R0 | \(1.0\times10^{-10}\) | 4000 | 2000 | Existing baseline; reuse |
| R1 | \(3.0\times10^{-11}\) | 4000 | 2000 | ODE-tolerance intermediate |
| R2 | \(1.0\times10^{-11}\) | 4000 | 2000 | ODE-tolerance fine |
| R3 | \(1.0\times10^{-10}\) | 8000 | 2000 | Rate-grid intermediate |
| R4 | \(1.0\times10^{-10}\) | 16000 | 2000 | Rate-grid fine |
| R5 | \(1.0\times10^{-10}\) | 4000 | 4000 | Background-grid intermediate |
| R6 | \(1.0\times10^{-10}\) | 4000 | 8000 | Background-grid fine |
| R7 | \(3.0\times10^{-11}\) | 8000 | 4000 | Joint intermediate refinement |
| R8 | \(1.0\times10^{-11}\) | 16000 | 8000 | Joint fine refinement |

This is deliberately larger than a five-run “baseline plus one change per factor” matrix. Three levels per grid axis are needed to estimate an observed convergence order rather than merely report a two-point difference. The precision axis also has three levels, with decreasing rtol.

### Separate network-truncation control

\`R_NET_AMAX8\` is not a convergence rung. It uses the baseline numerical settings but runs \`network="large", amax=8\`. Its sole purpose is to compare common light nuclides in \`large\` and \`large, amax=8\`. It is a same-solver network-completeness diagnostic, not an independent solver and not a test of the heavy tail. Compare only shared species and observables; preserve the full-network result as primary.

## 3. Held-fixed inputs

Unless listed in the run matrix, all S0 settings remain frozen:

- PRIMAT source pin, Python backend, Python/NumPy/SciPy/threadpool environment and single-thread policy;
- \(\Omega_b h^2=0.02242\), \(T_\mathrm{start}=100\ \mathrm{MeV}\), \(T_\mathrm{end}=0.001\ \mathrm{MeV}\), \(\tau_n=878.4\ \mathrm{s}\);
- network \`large\`, \`amax=null\` for R0–R8;
- weak-rate sampling \`sampling_nTOp_per_decade=125\` and \`sampling_nTOp_thermal_per_decade=25\`;
- VEGAS settings \`vegas_n_eval=100000\`, \`vegas_n_itn=50\`;
- all QED, radiative, finite-mass, thermal, spectral-distortion and incomplete-decoupling flags;
- all physical constants, rate central values, reaction set, nuclide data and upstream tables.

No \(\Omega_b h^2\), \(\tau_n\), nuclear-rate normalization, rate variation, Monte-Carlo, observational likelihood or cosmological-model parameter is scanned. S0-N1 is strictly a numerical-resolution study.

## 4. Cache identity is part of the experiment

A naive “reuse the old cache” implementation would invalidate the comparison.

At the pinned upstream:

- \`rate_grid_npts\` does not change the \(n\leftrightarrow p\) weak-rate fingerprints.
- \`numerical_precision\` does not change those fingerprints.
- \`sampling_temperature_per_decade\` **does** enter the non-thermal weak-rate fingerprint, because the background \(T_\nu(T_\gamma)\) interpolation grid is consumed by the weak-rate calculation.
- \`sampling_temperature_per_decade\` is deliberately absent from the thermal CCRTh fingerprint. The thermal cache should therefore remain the same, but its fingerprint and file hash must still be checked at runtime.

Consequently, the runs at background-grid density 4000 and 8000 require their own non-thermal weak-rate cache artifacts. Generate each such table once under the pinned source and an isolated cache overlay; record the computed fingerprint, source configuration, SHA-256 and Git blob SHA; then freeze and reuse the exact same bytes for every run at that background-grid density. R5 and R7 share the 4000-grid cache; R6 and R8 share the 8000-grid cache. R0–R4 and \`R_NET_AMAX8\` retain the S0 baseline cache.

The baseline non-thermal weak table is \`nTOp_7e3af87bd0404e0a.txt\` (Git blob \`f5111a85112e94a237ed73f28ef860876ee0f8ed\`). The baseline thermal table is \`nTOp_thermal_cfdb4d324bb5651f.txt\` (Git blob \`e3a8b6782393df73a9140e05bd3941ff135af2c9\`). For new background grids, do not guess fingerprints: compute them with the pinned \`PRIMATConfig\` and require an exact cache-preflight receipt before any solver starts.

The implementation must refuse:
- any weak-cache regeneration for a fingerprint already frozen;
- any unexpected cache file, changed hash, fallback to another upstream file, or silent cache miss during a production solve;
- any thermal-cache recomputation or change in thermal fingerprint;
- any reuse of the 2000-grid non-thermal table at 4000 or 8000.

All caches live in run-specific overlays; the pinned upstream checkout stays clean and unchanged. A cache-build operation is not silently included in a solver run: it gets its own receipt, runtime accounting and freeze.

## 5. Preregistered numerical budgets

The following are **project-internal numerical-stability budgets**, not published PRIMAT physics uncertainties. They are set before R1–R8 are observed at one tenth of the corresponding pinned PRIMAT regression tolerances where available.

| Quantity | Numerical budget for a refined result relative to R0 |
|---|---:|
| \(Y_p^\mathrm{BBN}\) | absolute difference \(\le 1.0\times10^{-6}\) |
| D/H | absolute difference \(\le 3.0\times10^{-10}\) |
| \(N_\mathrm{eff}\) | absolute difference \(\le 1.0\times10^{-6}\) |
| He3/H and Li7/H | relative difference \(\le 1.0\times10^{-5}\) |
| Final \(Y_i\) for shared light species \(n,p,\mathrm{H2},\mathrm{H3},\mathrm{He3},\mathrm{He4},\mathrm{Li7},\mathrm{Be7}\) | relative difference \(\le 1.0\times10^{-5}\) |

For each quantity, report full-precision absolute and relative differences. Relative differences use a documented denominator and a numerical floor; no rounding to the displayed digits is permitted. If an observable is unavailable in a particular network, it is marked not applicable rather than imputed.

A strict numerical-stability PASS requires:
1. R2 and R8 each remain within the budgets relative to R0;
2. R4 and R6 each remain within the budgets relative to R0;
3. adjacent fine-rung differences (R2–R1, R4–R3, R6–R5, R8–R7) are within budget and do not show unresolved growth inconsistent with a plateau;
4. all solver, network, cache, raw-state and baryon-budget integrity gates pass;
5. no unexplained non-finite values, solver failure, missing era/species, or cache mutation occurs.

R7/R8 are not allowed to “cancel out” a failure on an individual axis: every one-factor fine result has its own gate. Interaction terms are reported separately. A large interaction triggers review even if the final joint difference happens to be small.

The pinned PRIMAT test tolerances used as the scale for these internal budgets are \(10^{-5}\) absolute for \(Y_p\), \(3\times10^{-9}\) absolute for D/H, \(10^{-5}\) absolute for \(N_\mathrm{eff}\), and \(10^{-4}\) relative for the quoted light-nuclide regression values. These originate in the pinned upstream test suite; they are not ToV acceptance criteria.

## 6. Convergence analysis

For rate-grid and background-grid sweeps, calculate the observed order for each observable from the three levels:

\[
p_\mathrm{obs} =
\log_2\left(
\frac{|Q_{N}-Q_{2N}|}{|Q_{2N}-Q_{4N}|}
\right).
\]

Use the actual grid values and report signed increments as well as the ratio. The upstream documents second-order behaviour for these interpolation grids; \(p_\mathrm{obs}\) is a diagnostic, not a forced fit. If the denominator is zero or at roundoff, report a plateau/undefined order explicitly. If increments change sign, grow under refinement, or yield an implausible order, mark the axis REVIEW_REQUIRED; do not silently discard it or force \(p=2\).

For the ODE-tolerance sweep, report \(|Q_{R1}-Q_{R0}|\), \(|Q_{R2}-Q_{R1}|\), and \(|Q_{R2}-Q_{R0}|\). Do not apply the grid-order formula to rtol. If tightening rtol does not reduce the change, or if fixed absolute tolerances may dominate, label the result unresolved and design an atol-specific follow-up.

For the joint runs, report medium and fine interaction residuals for each observable:

\[
I_\mathrm{mid} =
(Q_{R7}-Q_{R0}) -
[(Q_{R1}-Q_{R0})+(Q_{R3}-Q_{R0})+(Q_{R5}-Q_{R0})],
\]

\[
I_\mathrm{fine} =
(Q_{R8}-Q_{R0}) -
[(Q_{R2}-Q_{R0})+(Q_{R4}-Q_{R0})+(Q_{R6}-Q_{R0})].
\]

These are diagnostics of non-additivity among numerical controls, not physical interactions. They must be reported whether small or large.

## 7. Trajectories and invariants

Final abundances alone are not enough. Each run must preserve the three era raw solver arrays and dense abundance traces, with species order and temperature/time coordinates. Compare the shared light-species trajectories \(Y_i(T)\) on common, preregistered logarithmic temperature samples within each era. Report per-species maximum absolute and relative deviations, the location of each maximum, and the denominator/floor rule. Do not compare trajectories at equal cosmic time when the background grid itself has changed; temperature is the common independent coordinate for this comparison.

The baryon budget must be decomposed from **raw, pre-clamp arrays**, not compressed into one final residual:

- \(B=\sum_i A_iY_i\) at the initial and final raw solver states of every era;
- HT integration drift;
- the HT→MT Saha-seed increment;
- MT integration drift;
- MT→LT state-transfer/projection increment;
- LT integration drift;
- post-solver clamp/zero-fill increment, reported separately.

The pinned PRIMAT code intentionally adds the MT composite Saha seeds on top of the HT \(n+p\) state without renormalizing it. This produces a tiny, known baryon-budget step at HT→MT; upstream explicitly says renormalizing would perturb its reference numbers. S0-N1 must reproduce and report that increment, **not remove it**. In-era drift and handoff increment must not be conflated. No renormalization is allowed.

## 8. Required artifacts

The execution implementation must produce, at minimum:

- \`N1_PREREGISTRATION.json\` — immutable copy of this preregistration and all matrix values;
- \`RUN_MATRIX.json\` — resolved config, run identity and cache identity for every R0–R8 and \`R_NET_AMAX8\`;
- one execution manifest, process receipt, solver result, per-era raw arrays and dense trace per newly executed run;
- \`CACHE_PREFLIGHT.json\` and immutable receipts for all new weak-cache tables;
- \`BARYON_BUDGET.json\` — era and handoff decomposition for every run;
- \`CONVERGENCE_SUMMARY.json\` — per-observable deltas, observed orders, fine-rung gates, interaction residuals and final status;
- \`NETWORK_COMPARISON.json\` — shared-light-species comparison for \`large\` versus \`large, amax=8\`;
- \`ARTIFACTS.json\` — hashes of every published artifact, with its own checksum handled separately as in S0.

Every result must bind to the frozen PRIMAT commit, exact run-config SHA-256, code commit, dependency versions, platform, solver/backend, all cache fingerprints and file hashes, and the effective rtol/atol for every era.

## 9. Interpretation rules

- A repeatability PASS is not a convergence PASS.
- A convergence PASS is numerical evidence for this pinned code, rate compilation, background prescription and selected input point. It is not physical uncertainty propagation.
- \`R_NET_AMAX8\` is a network-truncation comparison; it does not establish independent-solver agreement.
- The heavy tail, including \(Y_\mathrm{CNO}\), remains diagnostic only; it is not used as a high-precision acceptance target.
- No likelihood fit, BBN observational comparison, S1/S2/BH1/S3 calculation, independent solver, or ToV “now” claim is part of S0-N1.
- No result may be described as scientific acceptance or evidence for CCC+TL merely because it passes the numerical gates.

The machine-readable preregistration is [N1_PREREGISTRATION.json](N1_PREREGISTRATION.json); artifact and metric definitions are in [OUTPUT_CONTRACT.md](OUTPUT_CONTRACT.md). Execution remains disabled in this design PR.
