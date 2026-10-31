# E002d: independent audit

Start with RESULT.md. The production report is immutable at
`071e15ebc37227b1549e660121bc735a1d86cb13`, under
`results/E002d_PROD_v003_r001/`. Production source is
`1f12d2f56145a30d2066f4b9f53592ebdc8a96e9`.

Download run.json and every file listed in its files mapping from that same GitHub ref, preserving exact bytes and paths under CACHE. For files exceeding the Contents API inline limit, resolve their blob SHA at the pinned ref and fetch that blob. No VM fallback is used for report verification.

From repository root, with NumPy and SciPy installed:

```
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python analysis/E002d_PROD_v003_r001/verify_report.py CACHE
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python analysis/E002d_PROD_v003_r001/analyze.py CACHE
```

The second command writes analysis.json and its lossless analysis.json.gz. The compressed version is committed. Hashes of both representations are in provenance.json. All A/B/C tables and arithmetic decompositions use the GitHub export.

For the separately authorized full-state check, fetch exactly the ten VM files listed in full_data_manifest.json and verify SHA256/size. Store each as FULL_CACHE/ID.npz. Do not substitute these files for missing GitHub report artifacts.

```
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python analysis/E002d_PROD_v003_r001/full_state_check.py CACHE FULL_CACHE
```

This builds the pinned generators and checks saved states, not time evolution or a fresh steady-state solve. It verifies the particle-hole/reflection covariance on the complete sparse generators and its relation to stationary currents.

The full archive remains on the VM. This directory contains audit scripts, evidence and conclusions, not a replacement production report. Scientific acceptance remains with the user. The 10-state sample does not certify every full history; reported full-grid quality gates are not all independently rerun. Error bands are the protocol's engineering tolerances, not statistical confidence intervals.
