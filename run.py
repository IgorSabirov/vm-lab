"""Small deterministic integration check; not a scientific model."""
import json
import os
from pathlib import Path
import uuid
from reporting import write_report

config = json.loads(Path(__file__).with_name('config.json').read_text())
value = sum(config['numbers'])
result = {
    'actual': value,
    'expected': config['expected_sum'],
    'ok': value == config['expected_sum'],
    'source_commit': os.environ['VM_SOURCE_COMMIT'],
    'run_id': os.environ['VM_JOB_ID'],
    'execution_nonce': str(uuid.uuid4()),
}
write_report(config, result)
print('INTEGRATION_RESULT ' + json.dumps(result), flush=True)
if config.get('mode', 'success') == 'expected_failure':
    print('EXPECTED_TEST_FAILURE: requested exit code 7', flush=True)
    raise SystemExit(7)
if not result['ok']:
    raise SystemExit(1)
