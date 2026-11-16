# BH1: strong-coupling thermal AdS and Hawking-Page saddle review

This branch is an analytical/source update only. No new machine run, BH1/BBN production run or VM job was performed by this update.

## Main documents

- [Synthesis report](REPORT.md)
- [Consolidated null-closure status (0/8 fully closed; 3/8 narrowed)](NULL_CLOSURE_STATUS_20261116.md)
- [A14/A15c reconciliation: S1=S2, BAD double subtraction rejected](A14_A15C_RECONCILIATION_20261116.md)
- [A∞ spectral audit and k=2 thermal-character erratum](A_INFINITY_SPECTRAL_AUDIT_20261116.md)
- [Neighbor review addendum: K1, B∞ normalization and conditional bounds](NEIGHBOR_REVIEW_ADDENDUM_20261116.md)
- [Machine-readable review ledger](NEIGHBOR_REVIEW_CHECKS.json)
- [K1: HP saddles, Euclidean bounce and finite-N crossover](K1_CONTRACT.md)
- [A∞: thermal AdS KK gas contract](AINF_KK_GAS_CONTRACT.md)
- [B∞: classical black-hole thermodynamics and entropy normalization](B_INFINITY_CONTRACT.md)
- [Primary source manifest](SOURCES.json)
- [Machine-readable branch status](STATUS.json)

## Branch distinction

- A' = free zero-coupling confined branch (lambda=0).
- A∞ = strong-coupling thermal AdS with the type-IIB supergravity KK gas.
- B∞ = large AdS5-Schwarzschild black hole.

The empty common-chi domain applies only to A' versus B∞, not to A∞ versus B∞.

## Latest A∞ audit

- 10D Weyl phase-space derivation gives cumulative count 256*epsilon^9/181440.
- Continuous density is 4/315*epsilon^8; discrete half-step level count is 2/315*epsilon^8.
- Peer reports dim M_k=256*dim[0,k-2,0] for k=2..46.
- A13 grading is peer-reported pass; A14 source-match for k=2,3,4 is reported by the research-session checker; committed checker/output provenance is pending.
- The preliminary 291/256 alarm is resolved: 291 is the formal positive-primary count before shortening; 35 null descendants are removed by the short character. S1 and S2 are equivalent; BAD double-subtracts.
- S1 baseline lnZ(chi_HP)≈2.63 is peer/research-session reported and source-character supported; BAD value 2.62211017 is rejected. Repository runner and clean rerun are still pending.
- A15c research-session run at kmax=150, epsilon=120 reports 0.195% local-density deviation and 2.139% cumulative deviation; acceptance depends on declared tolerance, and committed runner/output provenance is pending.
- The high-energy Weyl coefficient A=512.008725... is analytically supported under the stated boson/fermion asymptotic assumption; finite-chi A∞ thermodynamics is not yet accepted.

Historical unsupported A' numerical claims remain quarantined by the erratum in the A' folder. No scientific acceptance is promoted and main is untouched.
