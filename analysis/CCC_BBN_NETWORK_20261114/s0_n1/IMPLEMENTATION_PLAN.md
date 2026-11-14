# S0-N1 implementation and execution plan

**Status:** execution implementation complete; see PRELAUNCH_RESOLUTION.md. No R1–R8 output existed when v1.1 was frozen.
**Execution switch:** enabled by the current conditional launch instruction; source/cache/environment/resource gates remain mandatory before production.

## Phase 0 — Ratify the question and thresholds

Before writing an execution trigger, review and accept or amend:

1. the R0–R8 matrix in RUN_MATRIX.json;
2. the separate R_NET_AMAX8 control;
3. the numerical budgets and pass/inconclusive rules;
4. the cache-generation policy for background-grid values 4000 and 8000;
5. the raw trajectory and baryon-budget output contracts.

After ratification, record the accepted preregistration SHA-256 in a new freeze receipt. A change to a matrix value, threshold, cache rule, upstream pin, or held-fixed input after that point requires a new preregistration version; it must not be edited in place after results are observed.

## Phase 1 — Static source and configuration gate

Build an N1-specific launcher; do not patch or reuse the P2 worker in a way that changes PR #47's S0 provenance.

Before any integration:

- verify the repository branch and exact N1 design commit;
- verify the PRIMAT checkout is clean at the declared pin;
- verify the network inventory for full large and the separate large, amax=8 control;
- resolve each matrix row through the pinned PRIMATConfig;
- calculate the weak and thermal fingerprints from the actual pinned functions;
- verify that all non-matrix configuration values equal the held-fixed baseline;
- verify the expected solver methods and effective rtol/atol for HT, MT and LT;
- calculate and publish the full matrix/config hashes.

Any mismatch stops the workflow before a nuclear ODE solve.

## Phase 2 — Cache preparation and freezing

The baseline background-grid group BG2000 uses the frozen S0 cache files. BG4000 and BG8000 each need a new non-thermal n↔p table because the background sampling density contributes to the weak-rate fingerprint.

Recommended implementation: use a dedicated initialization-only process for each new group. Construct the pinned PRIMAT configuration and standard background with the correct group parameters; allow only the one expected non-thermal weak table to be created in that group's isolated cache overlay; then terminate before calling the nuclear-network solve. The process must fail if it attempts to recompute the thermal CCRTh table.

For each new cache group:

1. record the exact fingerprint dictionary and expected filename before initialization;
2. run the initialization-only builder once;
3. prove that the expected file was written by that process and that no other unapproved file appeared;
4. record its SHA-256, Git blob SHA, byte count, generator source/dependency identity and process receipt;
5. verify that the thermal fingerprint and thermal bytes are identical to the frozen S0 file;
6. publish a CACHE_FREEZE receipt and mark the cache immutable.

All R5/R7 runs then consume the exact same BG4000 file; all R6/R8 runs consume the exact same BG8000 file. The run worker must observe and verify actual cache reads. It must refuse a cache miss or generation after the freeze point.

This is necessary because PRIMAT's weak-rate cache is not just an optimization: it contains an interpolation table whose construction depends on the background neutrino-temperature interpolation grid.

## Phase 3 — Resource admission and execution

Use a dedicated N1 workflow and run directory. Do not reuse the P2 RUN_REQUEST or its budget as a blanket authorization for a larger series.

- First publish a target-runner calibration and a forecast covering cache preparation plus all solver runs.
- Get an explicit resource admission for that forecast before the first full solve.
- Run serially (one solver process at a time) so cache identity, machine load and resource accounting remain interpretable.
- Record every process attempt, including pre-solver failures, in a single append-only ledger.
- No automatic retries; no resume of an incomplete era; no budget reset between R1 and R8.
- Use the same pinned runner/dependencies/thread limits for all runs.
- Keep the existing R0 evidence read-only; do not recalculate or replace it.

R1 may be used as a first full-run timing calibration only after it has passed the ordinary pre-run admission gate. Any forecast revision for the remaining runs must be published with a time-stamped basis; it must not alter the physics matrix or numerical acceptance thresholds.

## Phase 4 — Capture and verify each run

The worker should be a controlled extension of the proven S0 worker architecture, with these additions:

- accept only an exact run ID from the preregistered matrix;
- reject any config difference outside that row's three numerical controls and the explicitly separate amax control;
- capture raw HT/MT/LT solver arrays before PRIMAT postprocessing;
- preserve dense Y_i(T) traces on the shared temperature samples;
- record actual rtol/atol, solver counters, era timings, memory and process exits;
- instrument and validate the exact files loaded for weak, thermal, electron-thermodynamic and QED caches;
- preserve partial artifacts and honest failure receipts if a process fails;
- never convert a failed integration into a physical negative result.

## Phase 5 — Independent postprocessing and convergence report

The read-only verifier must not call PRIMAT or re-integrate the ODE. It should:

1. validate hashes, run IDs, configs, environment, source pin and cache load receipts;
2. reconstruct final observables independently from stored result/raw arrays where possible;
3. compute the raw-array baryon budget with the HT→MT Saha increment separated from in-era drift;
4. align and compare trajectories in temperature, not equal cosmic time;
5. calculate one-factor deltas, grid convergence orders and joint interaction residuals;
6. compare large with large, amax=8 only on common light species;
7. evaluate every preregistered gate and emit an explicit PASS/FAIL/INCONCLUSIVE reason.

All reports must distinguish numerical convergence of the pinned solver from physical uncertainty and scientific acceptance.

## Phase 6 — Publication boundary

Publish the run package and evidence in a dedicated N1 PR stacked on the S0 branch. Keep PR #47 unchanged. Do not merge automatically, edit main, change R/C/L/U statuses, or set scientific acceptance true.

The execution package should include its own tests for:
- rejecting altered or unknown run IDs;
- rejecting unintended configuration changes;
- rejecting weak/thermal cache fingerprint mismatch and cache mutation;
- rejecting incomplete era arrays and non-finite solver values;
- detecting incorrect species ordering;
- detecting a deliberately corrupted baryon-budget decomposition;
- detecting a missing or modified artifact;
- distinguishing an expected Saha handoff increment from in-era baryon drift;
- refusing to mark convergence PASS when any one-factor fine-rung gate fails.

The current owner instruction authorizes this execution after implementation checks and the published target-machine admission pass. Scientific acceptance remains false.
