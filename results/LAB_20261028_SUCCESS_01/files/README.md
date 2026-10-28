# Integration test report

This is a transport test, not a scientific model.

- Run: `LAB_20261028_SUCCESS_01`
- Source commit: `a7c5ae61784a740e49c2134cf3eb892668dbc076`
- Expected sum: 10; actual: 10.
- Execution mode: `success`.
- Detailed data: 4096 records; 16 time bins; exact histogram and statistics.
- Full file: 32768 bytes retained on the VM; see `data_manifest.json`.

The actual process exit code is in the parent `run.json`. Mode `expected_failure` deliberately exits with code 7.
