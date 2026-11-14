# S0-N1 output contract

This document defines required execution evidence. The implemented workflow produces it; only published process receipts/results establish which runs completed.

## 1. Per-run identity and execution manifest

Every executed run must emit one immutable manifest containing:

- protocol ID and run ID;
- preregistration file SHA-256 and design commit SHA;
- run source commit SHA and the exact PRIMAT commit/tree;
- complete resolved PRIMAT configuration and configuration SHA-256;
- network species and channel inventory by era, including exact order;
- Python, NumPy, SciPy, threadpoolctl, OS/kernel, architecture, CPU affinity and BLAS/threadpool details;
- solver method, success/status/message, nfev/njev/nlu, steps and wall/CPU/RSS;
- actual per-era relative and absolute tolerances (do not infer LT rtol from the top-level numerical_precision label);
- all cache fingerprints, resolved source paths, SHA-256 and Git blob SHA for files actually loaded;
- cache snapshot before and after initialization/solve;
- hashes and sizes of raw arrays, traces, result and log files;
- explicit scientific_acceptance=false.

A run with a different PRIMAT pin, untracked source modification, changed dependency set, backend, physical input, correction flag, rate compilation, or undocumented cache source is not an N1 replicate. Stop and classify it as an execution-contract deviation.

## 2. Raw solver and trajectory payloads

Retain the raw, pre-postprocessing result for each era:

- RAW_HT.npz, RAW_MT.npz, RAW_LT.npz (or an equivalently lossless format);
- exact solver time vector and state matrix;
- exact species order associated with each state vector;
- a dense trace with 401 logarithmically spaced temperature samples over that era, with T_MeV, corresponding cosmic time, and Y_i(T) for every integrated species;
- solver success, method, effective tolerances and diagnostic counters.

The dense trace is for aligned comparisons and audit. It is not the adaptive integrator's complete internal-step history. The raw solver arrays remain authoritative for internal conservation and handoff calculations.

Trajectory alignment rule: compare Y_i(T) at the same T within the same era. Do not compare the same cosmic-time coordinate across different background-grid runs: the t(T) map is part of the changed numerical object. Report per species and era the maximum absolute difference and a normalized maximum:
\[
\epsilon_i^{\mathrm{traj}} =
\frac{\max_T |Y_i^{(r)}(T)-Y_i^{(R0)}(T)|}
{\max\{\max_T|Y_i^{(r)}(T)|,\max_T|Y_i^{(R0)}(T)|,10^{-30}\}}.
\]
Also report the temperature where each maximum occurs. This trajectory metric is diagnostic in the present preregistration; final-observable budgets remain the hard numerical gates.

## 3. BARYON_BUDGET.json

Calculate baryon number from raw abundance vectors:
\[
B(t)=\sum_{i\in\mathcal S} A_iY_i(t),\qquad A_i=N_i+Z_i.
\]
Use the nuclide N_i,Z_i values from the exact pinned PRIMAT configuration/data. Preserve solver arrays unmodified.

Required structure (illustrative JSON shape; field names are normative):

~~~json
{
  "schema": "vm-lab-s0-n1-baryon-budget-v1",
  "renormalization_applied": false,
  "mass_numbers_source": "pinned_PRIMAT_cfg.Nuclides",
  "runs": {
    "R1": {
      "eras": {
        "HT": {
          "species_order": ["n", "p"],
          "B_initial_raw": 1.0,
          "B_final_raw": 1.0,
          "integration_drift": 0.0
        },
        "MT": {
          "species_order": [],
          "B_initial_raw": 0.0,
          "B_final_raw": 0.0,
          "integration_drift": 0.0,
          "initial_composite_Saha_contribution": 0.0
        },
        "LT": {
          "species_order": [],
          "B_initial_raw": 0.0,
          "B_final_raw": 0.0,
          "integration_drift": 0.0
        }
      },
      "handoffs": {
        "HT_to_MT": {
          "B_before_raw": 0.0,
          "B_after_raw": 0.0,
          "delta_B": 0.0,
          "composite_Saha_sum_A_Y": 0.0,
          "renormalized": false
        },
        "MT_to_LT": {
          "B_before_raw": 0.0,
          "B_after_raw": 0.0,
          "delta_B": 0.0,
          "species_mapping_verified": true
        }
      },
      "postprocessing": {
        "B_LT_final_raw": 0.0,
        "B_final_reported": 0.0,
        "clamp_and_zero_fill_delta_B": 0.0
      },
      "closure": {
        "initial_B_minus_one": 0.0,
        "decomposed_final_B_minus_one": 0.0,
        "direct_final_B_minus_one": 0.0,
        "decomposition_roundoff_residual": 0.0
      }
    }
  }
}
~~~

The zeros above are schema placeholders, not expected measured values.

### Required decomposition

For each run, calculate:

1. HT initial B, HT final B, and HT integration drift B_HT,f − B_HT,i.
2. MT initial B, the HT→MT increment B_MT,i − B_HT,f, and the explicit composite Saha sum Σ_(i≠n,p) A_i Y_i^Saha.
3. MT final B and MT integration drift B_MT,f − B_MT,i.
4. LT initial B, the MT→LT transfer increment B_LT,i − B_MT,f, checked by matching species names and zero-filling only species absent from MT.
5. LT raw final B and LT integration drift B_LT,f − B_LT,i.
6. The separate change from raw LT final values to PRIMAT's postprocessed final result (negative-value clamp and any light-species zero-fill).

The decomposition must close, up to floating-point summation error:
\[
B_{\mathrm{final,reported}}-1 =
(B_{\mathrm{HT},i}-1)
+\Delta B_{\mathrm{HT}}
+\Delta B_{\mathrm{Saha}}
+\Delta B_{\mathrm{MT}}
+\Delta B_{\mathrm{MT\to LT}}
+\Delta B_{\mathrm{LT}}
+\Delta B_{\mathrm{post}}.
\]
Report both direct and decomposed totals and their discrepancy.

The HT→MT Saha term is expected to be a small positive contribution under the pinned implementation. It is a handoff term, not an ODE integration error. Do not renormalize the Saha-seeded MT vector, do not “correct” later eras by normalization, and do not hide this increment inside a single global residual. Acceptance checks for in-era drift apply to the individual era drifts; the handoff term is reported and interpreted separately.

## 4. CONVERGENCE_SUMMARY.json

For every observable, preserve full-precision values and calculate:

- absolute and relative Rk−R0 differences for all runs;
- signed adjacent increments along each one-factor sweep;
- observed grid order p_obs for rate-grid and background-grid axes, including the ratio used to obtain it;
- R1/R2 relative-tolerance response;
- medium and fine joint-interaction residuals;
- all trajectory diagnostics;
- each gate's status, its numeric threshold, measured value, and the exact source of that threshold.

Required observable set includes YPBBN, DoH, Neff, He3oH, Li7oH, and final Y_i for the shared light species n, p, H2, H3, He3, He4, Li7, Be7. Record unavailable values as null with a reason, never as zero.

For final light-species relative differences use:
\[
\epsilon_i^{\mathrm{final}} =
\frac{|Y_i^{(r)}-Y_i^{(R0)}|}
{\max(|Y_i^{(r)}|,|Y_i^{(R0)}|,10^{-300})}.
\]
The 10^-300 floor is frozen here; it is not to be tuned after seeing results.

Suggested top-level shape:

~~~json
{
  "schema": "vm-lab-s0-n1-convergence-summary-v1",
  "status": "NOT_RUN",
  "scientific_acceptance": false,
  "baseline_run": "R0",
  "observables": {},
  "axes": {
    "numerical_precision": {},
    "rate_grid_npts": {},
    "sampling_temperature_per_decade": {}
  },
  "joint_interactions": {
    "medium": {},
    "fine": {}
  },
  "trajectory_metrics": {},
  "gates": {},
  "interpretation": {
    "repeatability_is_not_convergence": true,
    "physical_uncertainty_was_not_propagated": true,
    "independent_solver_was_not_used": true
  }
}
~~~

## 5. NETWORK_COMPARISON.json

Compare R0 (large) with R_NET_AMAX8 (large, amax=8) at the same Ω_bh², τ_n, correction flags, background grid, rate grid, numerical precision and pinned environment. The comparison must:

- verify the actual species/channel inventory from the pinned source audit;
- compare only species integrated in both networks;
- report final absolute/relative differences and common-light-observable differences;
- apply the upstream NUCLIDE_REL_TOL=1e-4 only as a network-truncation diagnostic;
- label the result SAME_SOLVER_NETWORK_COMPARISON, never INDEPENDENT_SOLVER_VALIDATION.

The heavy species present only in large have no counterpart in amax=8; do not map missing nuclides to measured zero for the purpose of claiming agreement. Heavy-tail abundances remain diagnostic.

## 6. Cache evidence

CACHE_PREFLIGHT.json must record the exact computed weak and thermal fingerprint dictionaries and hashes for each cache group before the first integration. CACHE_FREEZE.json must pin for each cache artifact:

- cache group and configuration that generated it;
- fingerprint dictionary, fingerprint hash and filename;
- source PRIMAT commit and generator code hash;
- generator environment and process receipt;
- SHA-256, Git blob SHA, size and resolved path;
- the exact R runs permitted to consume it.

For BG4000 and BG8000, the non-thermal weak cache is generated once and frozen. R5/R7 must load the same BG4000 bytes; R6/R8 must load the same BG8000 bytes. All runs retain the same frozen thermal cache. The worker must instrument actual cache reads, not merely inspect filenames.

Any cache miss, recomputation, cache mutation, unexpected file, fingerprint mismatch or load from a path other than the frozen artifact is an engineering failure. Do not silently “repair” cache problems by generating new files mid-series.

## 7. Artifact manifest and status

ARTIFACTS.json must hash every result, receipt, raw array, trace, config, log and summary. As in S0, its own self-hash is not included in its own list; publish its SHA-256 separately in a final verification receipt.

The terminal status must distinguish at least:

- ENGINEERING_PASS / ENGINEERING_FAIL;
- NUMERICAL_CONVERGENCE_PASS / NUMERICAL_CONVERGENCE_FAIL / INCONCLUSIVE;
- CACHE_INTEGRITY_PASS / CACHE_INTEGRITY_FAIL;
- SCIENTIFIC_ACCEPTANCE=false.

Passing the numerical convergence gates means stability of this pinned PRIMAT implementation under the specified numerical refinements. It does not validate rate uncertainties, nuclear data provenance, physical model assumptions, CCC+TL, or ToV.
