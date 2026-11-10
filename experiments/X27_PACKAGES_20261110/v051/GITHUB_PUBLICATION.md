# GitHub publication and reproduction

The v0.5.1 implementation is published on the dedicated branch `x27/u010-v03-v051-implementation` under `experiments/x27_u010_v03_v051/`.

The full source bundle is stored in `source_bundle/parts/*.b64`. Reassemble it from the experiment directory:

```bash
cat source_bundle/parts/*.b64 | base64 -d > X27_U010_V03_v0.5.1_reference_package.zip
sha256sum -c source_bundle/ZIP_SHA256SUMS.txt
```

Then extract and run the commands in `README.md`. The archive SHA-256 is also recorded in `ZIP_SHA256SUMS.txt`.

The active GitHub Actions workflow is installed at repository root: `.github/workflows/x27-v051-tests.yml`. A copy/template is kept under `.github-workflow-template/` for the local package.

Publication does not mean `DESIGN_FROZEN`: G0 closure for the full intervention kernel and the four model-specific H-Q partitions remain unevaluated, R1 functional benefit remains unestablished, and G7 remains unauthorized.
