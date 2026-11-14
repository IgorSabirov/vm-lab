# S0/S1 prelaunch — bounded validation, 14 November 2026

Authorization: current user instruction «Исследуй, привлеки … и закрой все вопросы запуска» authorizes the necessary prelaunch audit, bounded calibration and conditional control. Permanent authorization covers publication to IgorSabirov/vm-lab. No merger or scientific acceptance is implied. Parent: CCC_BBN_NETWORK v0.1.2, PR #44, CCC_BBN_DRIFT and PRIMAT source contract.

## Executable scope

Pure Python PRIMAT at `6f7e5680614fb119d65a6c9c65a292240b27c61e`; direct `primat.main.PRIMAT` cannot select the C backend. Python/NumPy/SciPy and effective thread pools are recorded. `use_numba=False` is explicit; no installation or weak-rate regeneration. Input tables remain upstream; the repository holds references/hashes and our adapter/results only.

1. P0 high-precision small, fresh local plasma overlay.
2. P1 high-precision large A≤8, separate fresh overlay, then a second fresh process with that P1 overlay.
3. P1 refinement: tolerance 3e-11, nuclear grid 8000, background temperature sampling held at 2000; same weak tables. This measures the discretization envelope conditional on fixed background grid and upstream thermodynamic and weak caches, not uncertainty in those tables.
4. Freeze per-era, per-species tolerance before S1: `5 * max_T |Y_refined - Y_base| + 1e-10 * max_T |Y_base| + 1e-14`. Same 401 logarithmic temperatures per era; no interpolation across era boundaries. Final-observable tolerance uses the same rule. This is a conservative engineering envelope, not a statistical confidence interval.
5. P1 S1: constant f=3.66; exponential f=3.66 exp(alpha tc), alpha=-1.5426109418e-18 s^-1. A nonconstant diagnostic alpha=-1e-7 s^-1 may test the exact map separately; it is not a cosmological prediction.
6. Negative control: stretch the time–temperature relation by 3.66 while keeping all rates unchanged. It must disagree with the baseline beyond the frozen envelope. Changing an unused H callback alone is not a control.

P2: static enumeration only, no 59-species solve. No S2, Sη, BH1, parameter fit, Monte Carlo or independent-solver claim. C/Python parity is separate from author reference reproduction and same-backend repeatability.

## Source and resource gate

Freeze this harness and configs on GitHub before BBN. Each process records the immutable vm-lab commit, config, upstream commit/tree, hashes and effective defaults. Launcher sets one BLAS/OpenMP thread, address-space cap 4 GiB, per-file cap 128 MiB and output-tree cap 512 MiB. Unavailable cgroup quotas are recorded as unknown, not inferred from host RAM. No network or installs in worker.

First P0 is explicitly an **uncalibrated bounded probe**: central 60 s, engineering range 5–180 s, hard cap 240 s. Basis: upstream tests/test_regression.py describes ~60 s reference checks; README describes a faster tier; this machine has no Numba, so neither is treated as a measured runtime here. Subsequent process/package estimates must use the measured P0/P1 and are persisted before launch. All BBN workers in this prelaunch package share a cumulative wall budget of 600 s. A projected continuation exceeding the remaining package budget is not started locally; the full next workload must be reassessed for VM, without splitting to evade the threshold. Queue, editing and publication are separate from calculation time.

Small completed runs are durable checkpoints. No solver resume or automatic retry. On export failure, first recover saved solver data. Failures retain logs and timing. Reference or invariant failure prevents a success declaration. Runtime outside the forecast keeps REVIEW_REQUIRED and gets an explanation, never a rewritten forecast.

## Cache and numerical contract

Strict weak input blobs: `nTOp_7e3af87bd0404e0a.txt` = `f5111a85112e94a237ed73f28ef860876ee0f8ed`; `nTOp_thermal_cfdb4d324bb5651f.txt` = `e3a8b6782393df73a9140e05bd3941ff135af2c9`. Verify resolved paths, blob/SHA256, actual read events and unchanged hashes after execution. Missing or mismatched cache stops the run. Expected local creation is electron thermodynamics for 100 MeV; this is distinct from weak-rate regeneration. P0 and P1 cold caches must be separate.

Author tolerances: |delta YPBBN|≤1e-5, |delta D/H|≤3e-9. P0 targets .24699844 and 2.4358977e-5; P1 .24700179 and 2.4366098e-5. Same-backend repeatability is reported separately (exact equality where achieved). Baryon residual ≤1e-10; raw negative floor -1e-12 is explicitly numerical, with minima recorded before final clamping. Active nuclear interval only, not the upstream 100→10 MeV zero-filled output extension.

## S1 map and coverage

Let u be the standard kinetic time, with its existing origin, and tc the conditional transformed clock. `du/dtc=1/f(tc)`, u(0)=tc(0)=0. For alpha≠0: u=(1-exp(-alpha tc))/(alpha f0), tc=-log(1-alpha f0 u)/alpha. This fixes an executable clock; identification with Gupta's physical/metric clock is not established by the control.

Keep the standard plasma and NEVO history at corresponding temperature. Map t(T), T(t), a(t), rho_b(t), Tnu(t); do not divide rho_b. HT uses both weak callbacks divided once. MT/LT wrap the **complete assembled RHS and analytic Jacobian**, supplying the original weak callbacks and dividing the whole result once. Forward, reverse, detailed-balance caps, density powers, radioactive channels and neutron decay are therefore covered by the same outer factor. No rate buffers or source tables are mutated. Optional post-BBN DT evolution is disabled.

A source audit enumerates 13/67/428 LT channels including one n↔p channel, and the actual MT subsets. P2 coverage is structural only. Solver integration and numerical invariance are established only for executed profiles.

## Meaning of completion

Close implementation/prelaunch questions only for P0/P1 S0 and this conditional S1. Fundamental S2 dynamics, alpha-dependent nuclear QED, physical-clock interpretation, second solver, observational likelihood and BH1 remain separate research questions. A successful computation does not promote R/C/L/U or count as scientific acceptance.
