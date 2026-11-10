# X27 v0.5.1 — publication and CI record

**Repository:** `IgorSabirov/vm-lab`  
**Branch:** `x27/u010-v03-v051-implementation`  
**Implementation status:** `REFERENCE_IMPLEMENTATION / DESIGN_DRAFT / NOT_FROZEN`

## Published artifacts

- The executable source, tests and specification are stored in the source archive reconstructed from `source_bundle/parts/part-*.b64`.
- `source_bundle/SOURCE_BUNDLE_SHA256.txt` records the archive SHA-256.
- `source_bundle/README_REASSEMBLE.md` gives the exact extraction commands.
- The full local distribution ZIP contains generated validation reports and the full-package checksum list; it is supplied separately in the conversation.

The transport fragments were checked by Git blob SHA against the local fragments. The fragment originally called `part-001` is represented by seven ordered subfragments (`part-001-00` through `part-001-05`, with `part-001-04` split into two files). Shell glob ordering places these between part 000 and part 002; no duplicate full `part-001.b64` is present.

## GitHub Actions verification

Workflow: `.github/workflows/x27-v051-tests.yml`  
Run: [42788066073](https://github.com/IgorSabirov/vm-lab/actions/runs/42788066073)  
Commit: `c5468e2d73966b9fed84ce5c16278f52cc8729fd`  
Result: `success`.

The successful run explicitly completed these steps:

1. Reassemble source archive and verify SHA-256.
2. Extract source tree.
3. Compile source and tests with `compileall`.
4. Run unit tests: 42 passed.
5. Run exact smoke.
6. Upload generated diagnostic artifacts.

Smoke values from that run:

- 40 policy capability cells.
- E2: 6/6; positive controls: 9/9; negative controls: 4/4.
- Computed (E^*_{nominal}=3), (E^*_{robust}=4).
- R2 high-load functional contrast: PASS.
- R1 functional benefit for r0: NOT DEMONSTRATED.
- Full G0 intervention closure: NOT EVALUATED.
- Four model-specific H-Q partitions: NOT EVALUATED.

Artifact: `x27-v051-validation-42788066073` (GitHub Actions run artifact).

## Scientific and release boundary

This is a successful software/CI validation of the finite reference implementation, not a physical experiment. The current R1 limitation is retained as a negative/undemonstrated result. Full G0 and H-Q adapter/partitions remain outstanding; `DESIGN_FROZEN=false` and `G7_MAIN_RUN=NOT_AUTHORIZED`.
