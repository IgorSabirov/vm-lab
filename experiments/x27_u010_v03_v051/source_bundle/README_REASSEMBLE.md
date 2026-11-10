# Reassemble the X27 v0.5.1 source bundle

This directory contains the base64 transport parts of the gzip-compressed source archive.

Run from this directory:

```bash
cat parts/part-*.b64 | base64 -d > X27_U010_V03_v0.5.1_source_bundle.tar.gz
sha256sum -c SOURCE_BUNDLE_SHA256.txt
tar -tzf X27_U010_V03_v0.5.1_source_bundle.tar.gz | head
```

The source archive contains the v0.5.1 Python implementation, tests, specification files, README, scope limits and the v0.4.3 regression-baseline record. Detailed generated validation artefacts are included in the full ZIP supplied separately.
