# X27 v0.5.1 — local software validation summary

**Package version:** 0.5.1 reference implementation  
**Validation mode:** deterministic finite-kernel software smoke and regression tests  
**Scientific main run:** NOT EXECUTED  
**Design freeze:** NOT FROZEN

## Test record

| Check | Result |
|---|---:|
| v0.4.3 regression baseline | 41/41 |
| v0.5.1 unit tests | 42/42 |
| Python compileall | PASS |
| Capability matrix | 40 cases |
| E2 exact estimator checks | PASS |
| Positive controls | 9/9 |
| Negative controls | 4/4 core controls plus NC13/NC15/NC16 |

## Model diagnostics

| Result | Current status |
|---|---|
| Nominal dose threshold | 3 |
| Robust dose threshold | 4 |
| R2 high-load functional contrast | PASS in this kernel |
| R2 ordinary-load functional contrast | (TV_{func}=0) |
| Ordinary-load full state-profile contrast | (TV_{state}=1), diagnostic only |
| R1 functional benefit | NOT DEMONSTRATED |
| Full v0.5.1 G0 reachable closure | NOT EVALUATED |
| H-Q full model adapter | PENDING |
| G7 | NOT AUTHORIZED |

The R1 limitation is substantive: with the declared health rule, Task 1 leaves (h=1), and fixed repair (r_0) restores only (h=1). The no-repair branch may therefore remain functional under the ordinary load. The current code does not claim that R1 has demonstrated a functional improvement over R0.

The R2 high-load difference is conditional on the declared model rule (ell=2), (r_0\to h=1), (r_1\to h=2). It confirms the implementation of that finite model rule, not a physical repair mechanism.

## Reproduction

From the unpacked reference ZIP:

```bash
python -m compileall -q src tests
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m x27v051.cli smoke --output validation/smoke
```

A software-smoke PASS is not a scientific hypothesis PASS and does not authorize G7.
