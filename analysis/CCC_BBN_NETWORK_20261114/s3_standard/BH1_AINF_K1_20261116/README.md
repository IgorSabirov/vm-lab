# BH1: strong-coupling thermal AdS and Hawking-Page saddle review

This branch is an analytical/source update only. No new machine run, BH1/BBN production run or VM job was performed by this update.

## Main documents

- [Synthesis report](REPORT.md)
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
- A13 grading is peer-reported pass; A14 low-level content remains partial.
- The original positive-only k=2 thermal sum is invalid as implemented (291 states rather than 256).
- Peer signed-subtraction thermal values are provisional until the shortened k=2 character is explicitly matched to KRN.
- A15 remains trend-only pending tolerance and full primary-tower coverage.
- The high-energy Weyl coefficient A=512.008725... is analytically supported under the stated boson/fermion asymptotic assumption; finite-chi A∞ thermodynamics is not yet accepted.

Historical unsupported A' numerical claims remain quarantined by the erratum in the A' folder. No scientific acceptance is promoted and main is untouched.
