# Historical source snapshots — not the reconnect entry point

Use `../../../reconnect_vm.py` for the existing vm-compute installation.
These files preserve the actual attempts, including failed or destructive old
installation components. Do not run them merely because the IP changed.
No private keys, live tokens, ACME account files or scientific results are included.

The source manifest hashes the archived files without changes. The source of the
successful certificate/deploy/verification sequence is
`successful_finish_158_160_159_114.txt`.

For the historical API/worker test only, reconstruct its input in a temporary
working directory from `fresh_original/*_source.py` as JSON mapping each filename
stem to its UTF-8 content, save as `fresh_original_payload.json`, then run
`test_fresh_original_runtime.py` there. It starts only local test processes.
The historical TLS test expects sibling `vm_repair_dns.py` and the original
acme==5.8.0/cryptography/josepy environment; no dependency downloads are needed
for the current reconnect script's six standard-library tests.
