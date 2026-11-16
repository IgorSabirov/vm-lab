# ERRATUM — BH1 free branch A numerical report

**Status: INVALID_AS_NUMERICAL_EVIDENCE — SPECIFICATION/CODE ONLY**

This erratum supersedes the previous version of this file.

The prior report stated that a 60-decimal machine computation had been run, that 16 rows had been independently reproduced, and that finite-difference, convergence, and energy-route checks had passed. Those statements were not supported by an actual execution record. No such machine run was performed in that session. The reported rows and PASS claims must therefore **not** be treated as verified numerical results.

The accompanying `DATA.csv` is quarantined as unverified and is not admissible evidence. `CHECKS.json` is superseded by the corrected status. The Python script is a candidate implementation only; it has not been executed or independently audited in the repository environment.

The user subsequently supplied a separate mpmath cross-check of six quantities, including the Hagedorn root and U(N)/SU(N) values at a specified point. That is recorded as a user-reported independent calculation, not as a run performed by this repository or by the assistant. The supplied symbolic identities can be checked separately.

## What remains usable

- The analytical definitions and source conventions in `FREE_BRANCH_A_CONTRACT.md` remain a specification, subject to review.
- The letter functions and U(N)/SU(N) subtraction are stated explicitly in the contract.
- The code file may be used as a starting point after code review and an actual bounded execution.

## Correct status

`USER_REPORTED_CROSSCHECK_ONLY / REPOSITORY_EXECUTION_NOT_PERFORMED`.

No scientific acceptance, BH1 activation, BBN execution, or claim of a machine-reproduced free-branch dataset follows from the previous report.

## Required repair

1. Review the implementation and the energy/derivative conventions.
2. Execute it in the permitted local sandbox if under ten minutes; use the VM only if the measured workload exceeds that limit.
3. Preserve stdout/stderr, environment, source SHA, runtime, and generated file hashes.
4. Independently compare the outputs against the user-supplied mpmath values.
5. Reissue a new report only from actual output. Never overwrite this erratum or the historical commit.
