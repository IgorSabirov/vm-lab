# X26 R040 Analytic Bath — package index

## v0.2.0 integration patch

- Patch archive: `X26_ADD_R040_PATCH_v0_2.tar.xz`
- Archive SHA-256: `5f489ab68c4a08f4530aeaf244e6ea3937e32a8bf4ee6b3de01f6bea52edb8ef`
- Git blob SHA: `7549cb39801a54bd87c1f21e35dfb83351f73bd2`
- Overlay target: the v0.1.0 package archive below.
- Includes the conditional ADD→R040 mapping layer (Phi), coherent and thermal loading protocols (Psi), resource ledger, moving-projector transfer check, integrated CLI/runner, configuration template, model-postulate contract, release notes and patch application instructions.
- Scientific status: explicitly conditional model assumptions; this does not derive Phi/Psi from K1/K2 and is not a physical calibration or ADD-derived BIC result.

Apply the overlay to the v0.1.0 archive:
```sh
tar -xJf X26_R040_ANALYTIC_BATH_v0_1.tar.xz
tar -xJf X26_ADD_R040_PATCH_v0_2.tar.xz
```
The patch archive contains `APPLY_PATCH.md` with the full procedure and status limitations.

## Base v0.1.0 spectral package

- Archive: `X26_R040_ANALYTIC_BATH_v0_1.tar.xz`
- Archive SHA-256: `96aec2703f921d280e0fe5bc5915bc04b03cc8af31df9d4b0183d3c647807d0b`
- Payload Git blob SHA: `2cc59eac82c352594965545f84303191f2437b90`
- Original package technical checks: 24/24 unit/integration tests PASS; compileall PASS (reported at package preparation; not re-run for this publication).
- Default manifest preflight intentionally blocks main execution unless a runtime gate is provided.
- Conditional R040 trimer + imported homogeneous 1D tight-binding bath; NOT ADD-derived.

## Scope and non-claims

The integrated v0.2.0 layer makes the Phi/Psi assumptions explicit and executable for sandbox studies. It implements motif-to-parameter mapping, a motif-permutation control preserving the declared combinatorial invariants, coherent and thermal loading alternatives, explicit work/heat/entropy accounting, and a one-step moving dark-projector transport diagnostic. Missing physical coefficients and resource conversions remain marked as assumptions or `NOT_EVALUABLE`; the default full-run template remains fail-closed. No VM run, physical calibration, registry promotion, NOW change, or merge to main is implied by this patch.
