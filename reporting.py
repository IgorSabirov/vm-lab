"""Example detailed report with explicit coverage; full bytes stay on the VM."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import struct


def write_report(config, outcome):
    report, full = Path('report'), Path('full')
    report.mkdir(exist_ok=True)
    full.mkdir(exist_ok=True)
    n = int(config.get('bulk_items', 4096))
    if not 16 <= n <= 1000000:
        raise ValueError('bulk_items must be in 16..1000000')
    values = [outcome['actual'] + i % 101 for i in range(n)]
    raw = b''.join(struct.pack('<q', value) for value in values)
    (full / 'values.bin').write_bytes(raw)
    sorted_values = sorted(values)
    metrics = {**outcome, 'sample_count': n, 'mean': statistics.mean(values),
               'stddev': statistics.pstdev(values), 'min': min(values), 'max': max(values),
               'quantiles': {str(q): sorted_values[round(q * (n - 1))] for q in (0, .01, .25, .5, .75, .99, 1)},
               'uid': os.getuid(), 'mode': config.get('mode', 'success')}
    (report / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
    histogram = [{'value': value, 'count': values.count(value)} for value in sorted(set(values))]
    (report / 'distribution.json').write_text(json.dumps(histogram, indent=2) + '\n')
    width = math.ceil(n / 16)
    rows = []
    for start in range(0, n, width):
        block = values[start:start + width]
        rows.append([start, start + len(block) - 1, len(block), block[0], block[-1],
                     min(block), max(block), statistics.mean(block)])
    with (report / 'series.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['first_index', 'last_index', 'count', 'first', 'last', 'min', 'max', 'mean'])
        writer.writerows(rows)
    checks = [
        {'name': 'configured_sum', 'actual': outcome['actual'], 'expected': outcome['expected'], 'passed': outcome['ok']},
        {'name': 'series_coverage', 'actual': sum(row[2] for row in rows), 'expected': n, 'passed': sum(row[2] for row in rows) == n},
        {'name': 'histogram_coverage', 'actual': sum(row['count'] for row in histogram), 'expected': n, 'passed': sum(row['count'] for row in histogram) == n},
    ]
    (report / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    inventory = {
        'input_data': [],
        'full_files': [{'vm_path': 'results/' + outcome['run_id'] + '/full/values.bin',
                        'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'dtype': 'int64 little-endian', 'shape': [n]}],
        'selection': {'method': 'exact metrics and histogram; deterministic contiguous time bins',
                      'input_records': n, 'series_rows': len(rows), 'records_covered': sum(row[2] for row in rows),
                      'histogram_exact': True, 'extremes_preserved_per_bin': True,
                      'detail_not_published': 'individual sample order inside each bin; full values remain on VM'},
        'full_data_access': 'Only after a separate explicit instruction from the user',
    }
    (report / 'data_manifest.json').write_text(json.dumps(inventory, indent=2) + '\n')
    text = (
        '# Integration test report\n\n'
        'This is a transport test, not a scientific model.\n\n'
        f'- Run: `{outcome["run_id"]}`\n- Source commit: `{outcome["source_commit"]}`\n'
        f'- Expected sum: {outcome["expected"]}; actual: {outcome["actual"]}.\n'
        f'- Execution mode: `{config.get("mode", "success")}`.\n'
        f'- Detailed data: {n} records; {len(rows)} time bins; exact histogram and statistics.\n'
        f'- Full file: {len(raw)} bytes retained on the VM; see `data_manifest.json`.\n\n'
        'The actual process exit code is in the parent `run.json`. '
        'Mode `expected_failure` deliberately exits with code 7.\n'
    )
    (report / 'README.md').write_text(text)
