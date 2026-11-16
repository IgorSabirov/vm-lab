# BH1 free thermal branch A — numerical result

**Status: PARTIAL_NUMERICAL_REPRODUCTION_REVIEW_NOT_SCIENTIFIC_ACCEPTANCE**  
**Contract:** [FREE_BRANCH_A_CONTRACT.md](FREE_BRANCH_A_CONTRACT.md).  
**Computation:** arbitrary precision, 60 decimal digits, 300 terms in the primary table.

## Main result

The free confined large-N Hagedorn boundary is

`chi_H = 0.37966285875010346160949206147183603`,

with `|z_1(chi_H)-1| = 1.56e-61` at the reported precision. Values were computed for both U(N) and SU(N), at chi/chi_H = 0.10, 0.20, 0.40, 0.60, 0.80, 0.90, 0.95 and 0.98. The last point remains below the free pole; no value at or above the pole is used.

At chi/chi_H = 0.80 (chi = 0.3037302870000827692875936491774688), the results are:

| Group | C_A | C_A' |
|---|---:|---:|
| U(N) | 0.04488355769535196035108084850 | 1.139090197128859194537996742 |
| SU(N) | 0.01789753788077803194896273187 | 0.7050629043793956421793709670 |

The U(N)-SU(N) difference is not negligible. It is especially important at low temperature because the SU(N) character subtraction removes the decoupled U(1) contribution. The groups must therefore remain separately reported.

## Numerical checks

- Hagedorn root residual: 1.56e-61.
- At chi/chi_H = 0.80, increasing Nmax from 8 to 16 changes C_A and C_A' only in the last displayed digits; Nmax >= 24 is stable at the reported precision.
- The action-derivative result and the independent energy derivative dE/dT agree with 2*pi^2*C_A'; maximum absolute residual across the 16 primary rows is below 4.0e-59.
- Five-point finite-difference diagnostics converge as the step is reduced at chi/chi_H = 0.20, 0.80 and 0.98 for both groups. At 0.98, the second-derivative absolute error falls from about 1.46e-1 to 1.45e-5 as h/chi_H decreases from 1e-3 to 1e-4.
- An independent clean 60-dps implementation reproduced all 16 rows in DATA.csv exactly at stored precision.
- Both groups tend to zero in the tested low-temperature sequence chi = 0.02, 0.01, 0.005.

## Limits and remaining work

This is the free, zero-coupling, confined, leading-large-N thermal branch with the vacuum/Casimir contribution subtracted. It is not the interacting Hawking-Page branch B. It does not determine Delta C(chi), lambda, the absolute gravitational vacuum energy, the physical meaning of f, the S3 embedding, a transition trigger, kinetic law, portal collision terms, or any BBN prediction.

The cutoff study is strong at chi/chi_H = 0.80, but a formal analytic tail bound and a systematic cutoff study throughout a declared near-pole interval have not yet been supplied. Therefore the full contract acceptance gate is **not passed**. Status remains REVIEW/partial numerical reproduction; no BH1/BBN execution or scientific acceptance is authorized.
