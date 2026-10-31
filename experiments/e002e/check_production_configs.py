"""Dry configuration checks against the measured VM passport; never execute work."""
import copy
import json
import os
from pathlib import Path
from run import bind_source
from e002e_exp.plan import preflight, selected_work, workload
from e002e_exp.runtime import kernel_hash


def main():
    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    folder = root / 'experiments/e002e'
    cal = json.loads((folder / 'calibration_verification_final.json').read_text())
    os.environ['VM_SOURCE_COMMIT'] = cal['source_commit']
    result = {}
    for stage in ('G', 'baseline'):
        config = bind_source(json.loads((folder / f'production_{stage}_config.json').read_text()))
        work, environment = preflight(config, copy.deepcopy(cal['environment']))
        result[stage] = dict(status='PASS', workload=workload(work), environment=environment)
    config['stage'] = 'F2'
    config['forecast'] = cal['stage_budgets']['F2']
    config['expected_workload'] = workload(selected_work('F2'))
    try:
        preflight(config, copy.deepcopy(cal['environment']))
    except KeyError as exc:
        if exc.args != ('baseline_report',):
            raise
        result['F2'] = dict(status='CORRECTLY_BLOCKED', reason="Missing verified baseline_report; predictions are also absent")
    else:
        raise AssertionError('F2 passed without baseline and frozen predictions')
    result['kernel_sha256'] = kernel_hash()
    result['scope'] = 'Dry configuration checks only; no scientific execution; live resources and actual queue source SHA rechecked at launch'
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
