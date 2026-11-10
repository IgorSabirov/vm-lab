# X27 v0.5.1 — validation snapshot

**Type:** software validation only  
**Protocol state:** DESIGN_DRAFT / NOT_FROZEN / MAIN_RUN_NOT_EXECUTED  
**Scientific G7:** NOT AUTHORIZED

## Local package verification

- ZIP re-extracted and re-run: 42/42 tests passed.
- `compileall`: PASS.
- Smoke: PASS.
- Full-package checksum manifest: 56/56 entries.
- Source-only checksum manifest: 33/33 entries.

## Independent GitHub Actions verification

Workflow run: [42788066073](https://github.com/IgorSabirov/vm-lab/actions/runs/42788066073)  
Commit: `c5468e2d73966b9fed84ce5c16278f52cc8729fd`  
Conclusion: `success`.

The workflow successfully reassembled the committed base64 transport fragments, verified the source archive SHA-256, extracted the source tree, ran `compileall`, passed all 42 tests, ran the exact smoke and uploaded the generated diagnostic artifact `x27-v051-validation-42788066073`.

## Software result summary

| Item | Verified result |
|---|---:|
| Policy capability matrix | 40 cells |
| E2 | 6/6 |
| Positive controls | 9/9 |
| Negative controls | 4/4 |
| A2 computed calibration | PASS |
| Nominal energy threshold | 3 |
| Robust energy threshold | 4 |
| R2 high-load functional contrast | PASS |
| R1 repair functional benefit for r0 | NOT DEMONSTRATED |
| Full G0 intervention closure | NOT EVALUATED |
| Four model-specific H-Q partitions | NOT EVALUATED |
| DESIGN_FROZEN | NO |
| G7 main run | NOT AUTHORIZED |

The exact fresh-smoke report remains in the full local ZIP attachment as `x27_v051/validation/SMOKE_REPORT.json`; the full ZIP also contains the 40-row capability CSV, oracle/policy audits, dose sweep, R1/R2 contrasts, NC13/15/16 records and validation checksums.

Kernel SHA-256: `7f43b5da5131cbef51d3efc85ab6eb5aa662db4c113445bdf024f71d998daf4b`  
Specification-manifest SHA-256: `fe98a2e884c76088d38609991e2c53efd36b714743020329f5ba142512f8c0f7`  
GitHub source-archive SHA-256: `cd9970e05e7a03edcac97f8e861030e65b0f1cd249c7b270fb2069ba9dfafb04`

These results characterize this executable finite model and its software checks only. They are not evidence for a physical mechanism.
