# S0-N1 prelaunch resolution, 14 November 2026

The current user instruction authorizes implementation and conditional execution. The R0–R8 matrix, R_NET_AMAX8 and proposed numerical budgets are retained. No new physical model or fitted threshold is introduced. PR #47 and its baseline remain immutable.

| Question | Resolution | Evidence/gate |
|---|---|---|
| Exact source/baseline | PR #48 design 81e05d4; parent 81ca44e; PRIMAT 6f7e568; R0 never rerun | Source/config/baseline hashes before first worker |
| Typed cache inputs | Use float 100.0 from R0; design integer corrected | Static fingerprints computed, not guessed |
| Actual solver | LSODA; BDF family including _BDFDirectLU; actual rtol/atol captured | Every solver call checked before execution |
| Network control | P1 audit: LT 12 species/67 total channels; full P2: 59/428; MT 12/18 | Existing pinned RATE_COVERAGE and runtime identity check |
| Cache generation | BG2000 uses shipped weak table; BG4000/BG8000 each generated once; electron thermo prepared then frozen | Builder forbids thermal recompute, solve workers forbid all weak recompute and cache changes |
| Generator continuity | Direct BG2000 table reconstruction against original, no baseline solve | Target-machine gate before production; absolute floor avoids meaningless rejection below weak-rate noise floor |
| Trajectory alignment | Exact 401 R0 temperature coordinates per era, guarded endpoint roundtrip | Raw arrays retained; boundary clipping explicitly reported |
| Baryon error | Saha seed, in-era drift, MT-LT mapping and clamp separated | Independent raw-array reconstruction; no renormalization |
| Numerical decisions | Existing budgets retained; operational plateau/order/rtol rules added before results | Budget failure stays FAIL; unresolved order stays INCONCLUSIVE |
| Environment | Python 3.12.16, NumPy 2.3.5, SciPy 1.17.0, threadpoolctl 3.6.0; BLAS signature compared to R0 | Mismatch blocks cache/solver execution |
| Resources | Own target-machine maximum-grid probe; all nine solves included | Forecast and admission published before R1; hard package/process limits, no retries |

At implementation time no unresolved choice prevented conditional preparation. The target-machine observation below now identifies a concrete blocker. Generator closure, environment compatibility and measured resource admission are execution prerequisites: the workflow checks them and stops before R1 if any fails. A negative/inconclusive convergence result is a legitimate outcome, not a reason to change thresholds or silently add runs.

Static implementation checks pass locally. The local checks did not integrate BBN; all N1 numerical preparation and solves run on the GitHub-hosted VM because the package is projected above 600 s.

## Technical correction before any numerical worker

Request r1 stopped before cache preparation: threadpool enumeration ran before scipy.linalg was imported, so it did not include SciPy's BLAS pool present in the R0 manifest. The error was reproduced locally (one library before import, two after). The environment reader now explicitly loads both numerical libraries, records actual versus baseline environment even on rejection, and has a regression test. Request r2 is an explicit corrected launch; no solver/cache work from r1 is repeated. The matrix, thresholds and preregistration bytes are unchanged.

## Actual target-machine observation: unresolved baseline environment

The corrected request r2 loaded both BLAS libraries and still failed the exact signature check: OpenBLAS Haswell on AMD EPYC 7763 versus SkylakeX on the Intel R0 machine. Thus the missing-library defect was fixed, but compatibility has not been established. All numerical preparation/production remains unstarted. READINESS.json records the blocker and ENVIRONMENT_AMENDMENT_DRAFT.md specifies the one-control amendment or compatible-executor alternative. Execution switches are false pending this choice.
