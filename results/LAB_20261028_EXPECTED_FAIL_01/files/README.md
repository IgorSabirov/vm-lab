# Integration test report

This is a transport test, not a scientific model.

- Run: `LAB_20261028_EXPECTED_FAIL_01`
- Source commit: `5bccf44106b8015b07072863e35e544b19e85626`
- Expected sum: 120; actual: 120.
- Execution mode: `expected_failure`.
- Detailed data: 4096 records; 16 time bins; exact histogram and statistics.
- Full file: 32768 bytes retained on the VM; see `data_manifest.json`.

The actual process exit code is in the parent `run.json`. Mode `expected_failure` deliberately exits with code 7.
