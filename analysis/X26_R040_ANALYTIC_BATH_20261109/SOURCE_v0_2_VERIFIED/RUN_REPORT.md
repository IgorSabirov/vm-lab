# X26_R040_ANALYTIC_BATH — local package validation

**Recorded:** 2026-11-09  
**Class:** local technical verification only; no physical run and no VM submit.

- Unit/integration tests: **24/24 PASS**.
- Python compile check: PASS.
- Default manifest preflight: expected exit code 2; 13 blockers; submit remains blocked.
- Synthetic end-to-end fixtures exercise both a tuned conditional R040 case and a detuned case. Their output is explicitly test-only and is not included as a physical result.
- Target-VM calibration and runtime forecast: `NOT_EVALUABLE`.
- ADD-derived mapping `ADD -> H_d,V,W`: absent and not invented.
- Loading control: static no-loading negative control included; dynamic loading interface is separate and requires explicit control/resource models.

See `CHECKS.json` and `LOCAL_TESTS.log` for the recorded local verification. The
local duration is not transferable to the target VM.
