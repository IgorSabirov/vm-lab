# X27_U010_V03 — v0.5.1 reference implementation

**Status:** DESIGN_DRAFT / NOT_FROZEN / MAIN_RUN_NOT_EXECUTED  
**Validation class:** software smoke only. No physical experiment is claimed.

This is a new finite model, not a silent patch to v0.4.3. The full source package, specification files, tests and detailed local validation results are assembled from the adjacent source-bundle parts.

## Reassemble source package

From the repository root:

```bash
cd experiments/x27_u010_v03_v051
cat source_bundle/parts/part-*.b64 | base64 -d > X27_U010_V03_v0.5.1_source_bundle.tar.gz
sha256sum -c source_bundle/SOURCE_BUNDLE_SHA256.txt
tar -xzf X27_U010_V03_v0.5.1_source_bundle.tar.gz
```

The archive expands into `x27_v051/`. For the full ZIP with generated validation artefacts, use the separate conversation attachment `X27_U010_V03_v0.5.1_reference_package.zip`.

## Reproduce

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q src tests
x27v051 smoke --output validation
```

## Fresh verified result

The current source archive produced 42/42 passing unit tests, compileall PASS, and an exact smoke report with:

- 40 capability cells: 2 evaluator-only cases × 5 candidate policies × 4 memory/payload cells.
- E2: 6/6, PC: 9/9, NC: 4/4.
- (E^*_{nominal}=3), (E^*_{robust}=4).
- R2 functional high-load contrast PASS, with load-1 functional null control.
- R1 functional benefit **not demonstrated** for r0 under the current wear/cost rules.

Important incompletions: complete G0 for the full v0.5.1 intervention kernel and the four actual model H-Q partitions remain unevaluated. This package does not authorize G7.

## Interpretation boundary

The model demonstrates properties of the declared Python transition system only. It does not establish a physical memory, repair, autonomy or resource-reproduction mechanism. C's creation and transfer remain trusted exogenous prehistory; B-FULL, D2, R063 and X28 are out of scope.
