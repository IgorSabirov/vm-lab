# Validation record — X27 v0.4.3 regression-repair candidate

**Validation type:** software/unit/control regression only  
**Scientific main run:** NOT EXECUTED  
**Design freeze:** NOT FROZEN  
**Scope:** F1–F8, legacy H-Q scope labelling (F9/F10), NC13 and NC14; no v0.5 redesign.

## Reproduction

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
x27 smoke --output validation/smoke_report.json
```

In the validation environment, all **40/40 unit tests** passed; `compileall` passed; and the installed `x27` entry point returned help successfully. Editable installation passed with the preinstalled setuptools backend using `--no-build-isolation`. An isolated pip build could not download `setuptools>=68` because the execution environment had no package-index network access; this is recorded in `validation/ENVIRONMENT.txt`.

## Current regression results

| Check | Result |
|---|---:|
| Unit tests | 40 / 40 PASS |
| X27-A G0 reachable physical states | 132 / 350,000 PASS |
| X27-B-LITE G0 reachable physical states | 6,752 / 350,000 PASS |
| E2 checks | 6 / 6 PASS |
| Positive controls | 9 / 9 PASS |
| Negative controls | 14 / 14 PASS |
| Main scientific run | NOT EXECUTED |
| Design freeze / G7 | NOT AUTHORIZED |

The H-Q sidecars preserve the legacy calculations for reproducibility, but the B-LITE result is explicitly marked `LEGACY_R2_LIKE_CAUSAL_M_PROD_READ`, not an R1 result, not transferable to v0.5 and not publishable as a frozen H-Q result. The historical 11/79 class counts are scope-labelled diagnostics only.

## Implemented contracts

Readiness requires exactly `{omega_delay, omega_loss_E, omega_loss_M}`. Empty, duplicate, incomplete, extra, or non-enum scenario inputs are rejected. State fingerprints recursively serialize every nested dataclass field, including provenance and record identity. TV and transition laws accept only exact non-negative `int`/`Fraction` masses and require exact normalization. Task-1 checksum failures remain `INTEGRITY_ERROR`, distinct from `MISSING_READ_EVENT`. Delay start/end and Task-2 read times are explicit. PC7 computes TV over the full joint legacy R2 outcome profile and checks it against an independent direct sum; this does **not** create a functional repair contrast because the v0.4.2 profile difference remains in `U`. Producer provenance is object-specific for C-created A1, fixture-provided A2 and absent A0.

NC13 checks nested identity/provenance mutation detection; NC14 checks integrity-error versus missing-read classification. The H-Q observation map and legacy intervention context are explicitly labelled; no full causal-trace equivalence is claimed.

## Excluded by version discipline

This branch does not implement F11–F14 or the v0.5.1 redesign: no independent task oracle, policy selector, tri-level apparatus health, high-load repair intervention, component capacity `(5,3,3,3)`, energy dose sweep, or computed A2 calibration. Resource capacity remains 3; apparatus health remains binary. These changes belong in a separate v0.5 implementation branch after design freeze.

Machine-readable outcomes, source hashes, and the complete unit-test log are stored under `validation/`. All outputs describe software execution of a finite deterministic model; none establishes a physical X27 mechanism or authorizes G7.
