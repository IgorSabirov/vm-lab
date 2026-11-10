# X27_U010_V03 — v0.5.1 design and validation record

**Branch:** `x27/u010-v03-v051-design-and-validation`  
**Protocol:** `DESIGN_DRAFT / NOT_FROZEN`  
**Execution:** `SOFTWARE_SMOKE_VALIDATED / G7_NOT_AUTHORIZED`

This folder records the v0.5.1 design closure and local software validation. It is **not** a complete source-code release: the executable Python package is currently delivered as a separate ZIP attachment, and the source modules are not present in this GitHub folder. Do not attempt to run Python tests from this folder.

## Version boundaries

- **v0.4.3:** regression-repair baseline. It remains a separate version and must not absorb v0.5.1 design changes.
- **v0.5.1:** new model with independent oracle, capability-only policy repertoire, health-level repair, separate functional/state TV metrics, dose sweep, exact probability arithmetic and separate executor/evaluator/trace views.
- **G7:** remains blocked pending design freeze and independent source/specification audit.

## Local executable package

The complete package is provided as `X27_U010_V03_v0.5.1_reference_package.zip` in the conversation. Its SHA-256 is:

```
502dc3faf3e336f830fd236be3daf70335c083b083105937b586c80d67267c22
```

The source-only archive inside the local package has SHA-256:

```
1516caaa4cc27d4e0eafba97614a1b98da2f94ae9c40bd2c11cdf00930083595
```

Reproduction commands after extracting the ZIP:

```bash
python -m compileall -q src tests
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m x27v051.cli smoke --output validation/smoke
```

## Software validation (local package)

- v0.4.3 regression baseline: 41/41 tests passed.
- v0.5.1: 42/42 tests passed.
- `compileall`: PASS.
- Smoke: `SOFTWARE_SMOKE_VALIDATED`.
- Capability matrix: 40 policy/task/factorial cases.
- Dose thresholds in the declared finite kernel: nominal 3, robust 4.
- R2 high-load functional contrast: PASS in the implemented model.
- R1 functional benefit: NOT DEMONSTRATED.
- G0 for the complete v0.5.1 intervention kernel: NOT EVALUATED.
- H-Q model adapter: PENDING.
- G7: NOT AUTHORIZED.

These are software/model results, not evidence for a physical mechanism.

See `SPEC_CLOSURE_v051.md`, `VALIDATION_SUMMARY.md` and `GITHUB_PUBLICATION_STATUS.md` for the accepted arithmetic and publication limitations.
