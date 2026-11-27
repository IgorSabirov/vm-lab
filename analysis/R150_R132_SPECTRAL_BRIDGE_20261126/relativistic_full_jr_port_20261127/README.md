# N=6 full-Jr ring + fixed port: relativistic contact transfer

Conditional numerical realization of the R132-R133-R150 spectral bridge. This is not a calibrated physical-carrier claim.

## Reproduce

Run: python3 replay.py

Dependencies: Python 3, NumPy, SciPy.

The script generates:
- RESULTS.json: Mathieu coefficients, contact scan, level gaps, port probabilities, sensitivities and regulator checks.
- PHASE_SWEEP.csv: 129-point phase sweep for FD, Mathieu and the six-mode spectral cutoff.
- PARAMETER_SWEEPS.csv: temperature, relative energy-reference and diagnostic 1% potential-depth sweeps.
- SPECTRAL_CUTOFF_AUDIT.json: six-mode versus seven-mode hard-cutoff parity diagnostic.

The contact parameters are a diagnostic scan inherited from the existing replay model; they are not experimentally calibrated. The Gibbs observable is a one-particle canonical port occupation, not a many-body occupation probability.

No numerical 1-sigma errors are assigned to the energy-reference offset, potential depth, phase or temperature: no physical carrier and no measured covariance/error bars have been selected. Reported derivatives are sensitivities only.