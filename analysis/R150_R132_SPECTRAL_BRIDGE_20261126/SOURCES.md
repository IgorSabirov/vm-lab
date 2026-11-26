# Sources and provenance

Research branch: research/r150-r132-spectral-bridge-20261126  
Base branch: research/r141-r148-html  
Base commit: b17c871ce37697c8beb36bf295797b5161ab11d2

The report is based on the supplied research note dated 2026-11-26 and on the following repository sources as they existed at the base commit above.

| Source | Blob SHA at base commit | Role |
|---|---|---|
| analysis/R130_BH1_BBN_CONNECTION_20261117/REPORT.md | bdd3955a214d5761e15dfb23ed5faabbf3c07d92 | Named transition, physical embedding and BBN boundary |
| analysis/R132_ADD_YM_CCM_20261119/REPORT.md | c8711bf5d8d39831a396de0504f540714bf2ec64 | Incidence operator, spectral geometry and edge/vertex conventions |
| analysis/R133_LOOP_CONNES_20261120/REPORT.md | 8035bf53bd2941ff71e8322845c785197a1d3f8d | Changing graph, loop geometry and KMS limits |
| analysis/R135_PHYSICAL_SECTOR_X_20261120/REPORT.md | 84bff247c5e20c13444e73c427b763200d5d58dc | Thermodynamic constraints and physical sector X |
| analysis/R150_THREE_GENERATIONS/REPORT.md | 316b10a9a5567e7bdc0e4016f4e366e9e65e0f13 | R150 model status and current BBN boundary |
| analysis/R150_THREE_GENERATIONS/floquet/CORE.md | c70f87c5e044878563cb328cc46e86feec4fb549 | Active/passive carrier decomposition |
| analysis/R150_THREE_GENERATIONS/floquet/phase_bbn/network_bench/MODEL.md | d580845ade6b935ae7f1f56463a87b3b2de8665d | Hamiltonian, seams and network conventions |
| analysis/R150_THREE_GENERATIONS/floquet/phase_bbn/network_bench/graph.py | 579e7ff62318f0e40c0ac707b6790bb7f0208bd6 | Exact signed-step and diagonal-contact matrix used by the network bench |
| analysis/R150_THREE_GENERATIONS/floquet/phase_bbn/experiment_review/README.md | 7fb28da89055549dd62c1ff1f321e3779164f895 | E1–E6 limitations and BBN test status |
| analysis/R150_THREE_GENERATIONS/floquet/phase_bbn/NETWORK_RESULTS.md | 58015e6a532a8f7c9d9cec3d8af6e456951f526d | Network outputs and open physical inputs |

verify.py uses a self-contained standard-library implementation of the identities and finite sums in this report. It does not import the previous analysis notebooks, the original R150 production pipeline, PRIMAT or LINX. Thus its PASS is an independent numerical check of the formulas stated here, not an independent physical experiment or a re-run of all parent-card tests.

No new R identifier or scientific-acceptance status is created by this child report. The generated REGISTRY_LINKS/INDEX is intentionally not edited by hand; navigation is added by explicit links in each parent R report.


The full-contact audit ports the matrix construction from network_bench/graph.py. Its NumPy implementation and numerical receipt are full_contact_audit.py and FULL_CONTACT_CHECKS.json; it is a finite-matrix audit, not a BBN rerun.
