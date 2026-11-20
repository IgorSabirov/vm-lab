# Genealogy: PRIMAT/LINX adapters for the BBN bridge

На GitHub проверены две нативные точки, 17 пар на общих тепловых входах и шесть расчётов CLASS до ℓ=2500. Физический источник BH1 и наблюдательная подгонка остаются открытыми. [Прямые расчёты 20 ноября](PAIRED_RUN_20261120.md). Датированные состояния ниже относятся к указанным в них версиям.

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

1. Implemented the first strict validator: `validate_contract.py`. Six unit tests
   cover valid input, non-monotonic time, misaligned arrays, unknown species,
   stale hashes and non-finite values; all six passed in a local isolated test.
   JSON Schema alone cannot enforce all cross-array invariants.
2. The species/reaction equivalence map is implemented in `NETWORK_MAP.json`
   for PRIMAT small and LINX `key_PRIMAT_2023`. Numerical rate identity is open;
   do not infer it from matching species, stoichiometry or 8/12 counts.
3. Implement thin adapters only for capabilities confirmed by pinned upstream
   source inspection. Explicitly report unsupported background/weak-rate inputs.
4. Run native standard controls, then the frozen LINX identity pair, then the
   common-network comparison. Only then connect a physically selected BH1 history.

## R130 joins the physical interface

The [R130–BH1–BBN connection](../R130_BH1_BBN_CONNECTION_20261117/REPORT.md) links R126 → R130 evidence to the existing BH1/background input. R130 supplies dimensionless observables and C1/C2 controls; BH1 supplies conditional thermodynamic constraints. Neither is established as a physical realization of the other. The unimplemented physical map is explicit in [CONNECTION_CONTRACT.json](../R130_BH1_BBN_CONNECTION_20261117/CONNECTION_CONTRACT.json). Questions U006/U007/U010 stay OPEN; no new result number or scientific acceptance is assigned.

## 20 ноября. Родители внешних контролей

Burns → чувствительности D+D; Froustey–Pitrou–Volpe → спектры и слабые скорости; Bojowald–Das–Scherrer → внешний закон расширения; Bai–Korwar и Joseph–Kumar–Sandick → нагрев и совместные BBN/CMB-наблюдаемые. В качестве источников физического входа R132–R134 остаются условными. [Версии и границы применения](../NEIGHBOR_EXTERNAL_DATA_USE_20261119/BBN_DONORS_R131_R134.md) · [Численные контроли](../NEIGHBOR_EXTERNAL_DATA_USE_20261119/BBN_METHOD_TRANSFER.md).
