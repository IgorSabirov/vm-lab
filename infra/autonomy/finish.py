"""Close an Actions reservation after the scientific controller has exited."""
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone
try:
    from .admit import read_ledger, write_ledger
except ImportError:
    from admit import read_ledger, write_ledger


def close(ledger, reservation, conclusion, publication_sha):
    if conclusion not in {'success', 'failure', 'cancelled'}:
        raise ValueError('Unknown terminal job conclusion')
    updated = json.loads(json.dumps(ledger))
    found = False
    for row in updated['packages']:
        if row['id'] != reservation['id']:
            continue
        found = True
        for key in ('source_sha', 'execution_plan_sha256', 'workflow_run_id'):
            if row.get(key) != reservation.get(key):
                raise ValueError('Reservation identity mismatch')
        if row['status'] not in {'RESERVED', 'RUNNING'}:
            raise ValueError('Reservation is already terminal; preserve first evidence')
        row.update(status='COMPLETED' if conclusion == 'success' else 'FAILED',
                   execution_conclusion=conclusion, publication_sha=publication_sha,
                   finished_utc=datetime.now(timezone.utc).isoformat(), scientific_acceptance=False)
    if not found:
        raise ValueError('Missing reservation')
    return updated


def main():
    path = Path(os.environ['RUNNER_TEMP'], 'autonomy-budget.json')
    if not path.exists():
        return
    admission = json.loads(path.read_text())
    if not admission.get('execute'):
        return
    reservation = admission['reservation']
    if reservation['workflow_run_id'] != int(os.environ['GITHUB_RUN_ID']):
        raise ValueError('Wrong workflow run')
    publication_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    for _ in range(3):
        ledger, expected = read_ledger()
        updated = close(ledger, reservation, os.environ['EXECUTION_CONCLUSION'], publication_sha)
        if write_ledger(updated, expected):
            return
    raise ValueError('Cannot close reservation; preserve it until live status is reconciled')


if __name__ == '__main__':
    main()
