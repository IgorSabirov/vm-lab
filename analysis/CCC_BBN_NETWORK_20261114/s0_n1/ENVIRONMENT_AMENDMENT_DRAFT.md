> Current decision: owner authorized launch with R_ENV. Protocol v1.2 is enabled; ten strict integrations use the same frozen target environment. R0 stays immutable. Earlier blocked/proposed statements below are historical.

# Proposed environment control — decision required, not enabled

## Observed problem

The existing R0 was computed on Intel Xeon 6975P-C with OpenBLAS 0.3.30 SkylakeX kernels. The newly allocated GitHub-hosted VM is AMD EPYC 7763 with OpenBLAS 0.3.30 Haswell kernels. Python 3.12.16, NumPy 2.3.5, SciPy 1.17.0, threadpoolctl 3.6.0 and one-thread limits agree. Both NumPy and SciPy libraries were explicitly loaded in the corrected check. The mismatch is real; do not suppress it or force an unsupported instruction set.

R1–R8, R_NET_AMAX8 and all cache builders have **not started**. Failed requests r1/r2 are retained. R1/R2 in request names must not be confused with numerical run IDs R1/R2.

## Recommended amendment: one extra R_ENV control

This proposal changes the earlier statement that the existing R0 alone supplies the baseline; it therefore remains a draft for the owner's decision.

| Role | Configuration | Environment | Use |
|---|---|---|---|
| R0 | Existing P2 COLD | Historical Intel/SkylakeX | Immutable historical reference, never overwritten |
| R_ENV | Exact R0 physical and numerical configuration | Same allocated machine/libraries as R1–R8 | Measure environment displacement and provide matched convergence anchor |
| R1–R8 | Original preregistered refinements | Same machine as R_ENV | Primary increments/order/joint effects relative to R_ENV |
| R_NET_AMAX8 | Original network control | Same machine as R_ENV | Network comparison against full R_ENV |

The R_ENV configuration is numerical_precision=1e-10, rate_grid_npts=4000, sampling_temperature_per_decade=2000, full 59-species/428-channel network, original frozen weak/thermal tables, unchanged physical constants/correction flags and absolute tolerances. This is one additional full integration, not a replacement for stored R0.

Before launch, freeze a new protocol version. Keep every existing observable budget unchanged. Report R_ENV−R0 separately as environment sensitivity; keep historical Rk−R0 differences as diagnostics. Do not classify those cross-environment differences as pure grid/rtol errors. For primary convergence/order tests substitute R_ENV for R0 consistently. All runs stay on the same target machine with the same BLAS signature. Recalculate the target-machine forecast for **ten strict integrations**, within a newly published admission; no implicit budget increase.

R_ENV cannot constitute independent-solver validation or scientific acceptance. If its displacement exceeds the predeclared stability budgets, retain an unresolved environment issue and do not declare baseline robustness. Even a tiny displacement does not erase the fact that the environments differed.

## Alternative: keep the original nine-run matrix

Provide an executor supporting and selecting the original SkylakeX BLAS kernels with the same dependencies. Recheck the full environment before calibration. A generic ubuntu-24.04 label does not itself pin the CPU. Do not repeatedly launch speculative jobs merely to obtain a different CPU, and do not force SkylakeX on the observed incompatible AMD machine.

No option is activated by this document. The current execution switches are false.
