# X27 v0.4.3 regression-repair source bundle

**Status:** REGRESSION_CANDIDATE / SOFTWARE_VALIDATED / NOT_FROZEN  
**Base:** v0.4.2 reference commit `91e1e6d32590ed5237b86704982d7fddc51e44c1`  
**Branch:** `x27/u010-v03-v043-regression-repair`

This directory stores the source bundle as ordered Base64 parts. Reassemble the original `tar.xz` archive from the repository root:

```bash
cat experiments/x27_u010_v03_v043_bundle/parts/part-*.b64 | base64 -d > X27_U010_V03_v0.4.3_source_bundle.tar.xz
sha256sum -c experiments/x27_u010_v03_v043_bundle/SOURCE_BUNDLE_SHA256.txt
mkdir -p x27_u010_v03_v043_source
tar -xJf X27_U010_V03_v0.4.3_source_bundle.tar.xz -C x27_u010_v03_v043_source
```

The reconstructed archive SHA-256 is:

`cfca20d52dc187397651f36443cc9d02aa56537fb41cbe8bc6d22833efe50f32`

The bundle contains the Python package, regression tests, model manifest, regression delta, README, validation note and package SHA256SUMS.

This branch is a regression repair only. F11–F15, oracle/policy redesign, tri-level apparatus health, high-load functional repair, component capacity `(5,3,3,3)` and energy dose sweep remain deferred to v0.5. No physical main run was executed; G7 is not authorized.
