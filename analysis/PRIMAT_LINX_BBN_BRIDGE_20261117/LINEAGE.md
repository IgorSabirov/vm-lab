# Genealogy: PRIMAT/LINX adapters for the BBN bridge

## Parent chain

```text
CCC+TL drift calculation
  analysis/CCC_BBN_DRIFT_20261113/REPORT.md
          |
          v
BH1 / thermodynamic embedding and energy-transfer contract
  analysis/CCC_BBN_NETWORK_20261114/s3_standard/bh_bridge_20261115/
          |
          v
Canonical cosmological BBN input
  BBNHistory + NuclearRateSet
          |
     +----+----+
     |         |
     v         v
  PRIMAT      LINX
  pinned      pinned
  upstream    upstream + D+D adapter
     |         |
     +----+----+
          |
          v
cross-backend observables, residuals and uncertainty propagation
```

## Parent evidence

- CCC+TL drift and the conditional common-scaling argument:
  `analysis/CCC_BBN_DRIFT_20261113/REPORT.md`.
- BH1-to-cosmology thermodynamic bridge:
  `analysis/CCC_BBN_NETWORK_20261114/s3_standard/bh_bridge_20261115/BRIDGE_CONTRACT.json`
  and `REPORT.md`.
- PRIMAT pinned source and interface:
  `infra/external/sources/PRIMAT.json`,
  `infra/external/contracts/PRIMAT.json`,
  `analysis/PRIMAT_INTEGRATION_20261113/REPORT.md`.
- LINX D+D adapter and full-identity preparation:
  [PR #57](https://github.com/IgorSabirov/vm-lab/pull/57),
  upstream pin `bfba07c77a5fcba1cc772d42f2d9e9be8a542df8`,
  `BBN_IDENTITY_CONTRACT.json` at source commit
  `6b8710970f8b4291cce8c798f986865a984e8413`.

## New bridge artifacts

- `BRIDGE_CONTRACT.md`: common architecture, canonical inputs, adapter responsibilities, staged validation and failure classification.
- `BBN_HISTORY.schema.json`: machine-readable envelope for shared cosmological history, nuclear rates and provenance.

## Status discipline

This genealogy is a typed research dependency, not a claim of completed execution.
The BH1 physical embedding remains open. The PRIMAT contract remains DRAFT.
The LINX identity pair remains PREPARED_NOT_EXECUTED. Neither backend currently
has a demonstrated adapter that consumes the complete canonical history in this
new bridge. No BBN, GP, BH1 or cross-backend numerical execution is claimed.
No R/C/L/U status is promoted by these documents.

## Immediate implementation sequence

1. Build and test a strict validator for this schema, including cross-array length,
   monotonic-time, finite-value, unit and hash checks (JSON Schema alone cannot
   enforce all of these).
2. Generate the species/reaction equivalence map for PRIMAT small and LINX
   `key_PRIMAT_2023`; do not infer identity from the matching 8/12 counts.
3. Implement thin adapters only for capabilities confirmed by pinned upstream
   source inspection. Explicitly report unsupported background/weak-rate inputs.
4. Run native standard controls, then the frozen LINX identity pair, then the
   common-network comparison. Only then connect a physically selected BH1 history.
