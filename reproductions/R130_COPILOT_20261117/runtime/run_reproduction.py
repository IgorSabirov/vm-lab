"""Execute the immutable R130 package once; this entry point is called by Copilot."""
import csv
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
OUT = HERE / 'results'
WORK = OUT / 'analysis'
IGNORED = {'seconds', 'elapsed_seconds', 'measured_at_utc', 'peak_rss_kib',
           'environment', 'python', 'runtime_plan_actual', 'this_execution_code_seconds',
           'successful_phase_code_seconds', 'timing_note', 'forecast_code_seconds',
           'actual_over_forecast', 'prior_harness_failure'}

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k not in IGNORED}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value

def compare(a, b, path='', diffs=None):
    diffs = [] if diffs is None else diffs
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                diffs.append({'path': path+'/'+k, 'kind': 'missing_key'})
            else:
                compare(a[k], b[k], path+'/'+k, diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append({'path': path, 'kind': 'length'})
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, path+'/'+str(i), diffs)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, int) and isinstance(b, int):
            ok = a == b
        else:
            ok = math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)
        if not ok:
            diffs.append({'path': path, 'expected': a, 'actual': b})
    elif a != b:
        diffs.append({'path': path, 'expected': a, 'actual': b})
    return diffs

def check_raw():
    rows = []
    manifest = json.loads((HERE/'reference/RAW_DECODED_SHA256.json').read_text())
    for name, expected in manifest.items():
        p = WORK/'ADD_C1_SCIENCE_20261117'/name
        data = gzip.decompress(p.read_bytes()) if name.endswith('.gz') else p.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        rows.append({'path': name, 'expected_decoded_sha256': expected['sha256_decoded'],
                     'actual_decoded_sha256': actual, 'exact_match': actual == expected['sha256_decoded']})
    return rows

def main():
    # Refuse a repeated Copilot tool call rather than silently compute twice.
    OUT.mkdir(exist_ok=True)
    lock = OUT/'STARTED.json'
    with lock.open('x') as f:
        json.dump({'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}, f)
    import numpy
    import matplotlib
    receipt = {'status': 'RUNNING', 'executor': 'GitHub Actions, invoked by native Copilot CLI',
               'source_commit': os.environ.get('GITHUB_SHA'), 'source_payload_commit': '9e53090e6f288d16adc692e57a22ab7326459bf9',
               'run_id': os.environ.get('GITHUB_RUN_ID'), 'resume': False,
               'environment': {'python': sys.version, 'numpy': numpy.__version__, 'matplotlib': matplotlib.__version__,
                               'platform': platform.platform(), 'machine': platform.machine(), 'cpu_count': os.cpu_count()},
               'commands': [], 'historical_metadata_note': 'Copied scientific scripts retain historical platform/timing strings; this receipt identifies the actual clean GitHub execution.'}
    t0 = time.perf_counter()
    exit_code = 1
    try:
        manifest = json.loads((HERE/'SOURCE_MANIFEST.json').read_text())
        for name, expected in manifest.items():
            assert hashlib.sha256((HERE/'source'/name).read_bytes()).hexdigest() == expected, name
        shutil.copytree(HERE/'source', WORK)
        commands = [
            ['ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py'],
            ['ADD_C1_LOCAL_REPRO_20261117/run_block1.py', '--calibrate'],
            ['ADD_C1_LOCAL_REPRO_20261117/run_block1.py', '--run'],
            ['ADD_C1_SCIENCE_20261117/run_science.py', '--calibrate'],
            ['ADD_C1_SCIENCE_20261117/run_science.py', '--run'],
            ['ADD_C1_SCIENCE_20261117/verify_results.py'],
            ['ADD_C1_SCIENCE_20261117/plot_results.py']]
        env = {k: v for k, v in os.environ.items() if 'TOKEN' not in k and 'SECRET' not in k and not k.startswith('COPILOT_')}
        env.update(PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1', MPLBACKEND='Agg')
        for index, args in enumerate(commands):
            start = time.perf_counter()
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            with (OUT/f'{index:02d}.stdout.log').open('w') as stdout, (OUT/f'{index:02d}.stderr.log').open('w') as stderr:
                p = subprocess.run([sys.executable, *args], cwd=WORK, env=env, stdout=stdout, stderr=stderr)
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            row = {'argv': [sys.executable, *args], 'exit_code': p.returncode, 'wall_seconds': time.perf_counter()-start,
                   'cpu_seconds': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime}
            receipt['commands'].append(row)
            dump(OUT/'EXECUTION_RECEIPT.json', receipt)
            print(json.dumps(row), flush=True)
            if p.returncode:
                raise RuntimeError(f'Command {index} failed: {args}; see saved stderr/stdout')
        differences = []
        checked = []
        for p in sorted((HERE/'reference').glob('*/*.json')):
            rel = p.relative_to(HERE/'reference')
            q = WORK/rel
            if not q.is_file():
                raise FileNotFoundError(q)
            found = compare(clean(json.loads(p.read_text())), clean(json.loads(q.read_text())), str(rel))
            differences.extend(found)
            checked.append(str(rel))
        raw = check_raw()
        raw_differences = [x for x in raw if not x['exact_match']]
        comparison = {'status': 'MATCH' if not differences and not raw_differences else 'REVIEW_DIFFERENCES',
                      'json_files': checked, 'ignored_metadata_keys': sorted(IGNORED),
                      'json_float_rel_tol': 1e-12, 'json_float_abs_tol': 1e-9,
                      'differences': differences, 'raw_files': raw,
                      'raw_comparison': 'Exact SHA-256 after gzip decompression; any mismatch is REVIEW, never silently tolerated.'}
        dump(OUT/'COMPARISON.json', comparison)
        receipt['status'] = 'COMPLETE_' + comparison['status']
        receipt['scope'] = {'blocks': 3, 'operator_inputs': 6032, 'named_inputs': 5460, 'short_trajectories': 10920,
                            'short_steps': 1397760, 'long_trajectories_including_extensions': 30, 'long_steps_including_extensions': 147456}
        exit_code = 0
    except Exception:
        receipt['status'] = 'EXECUTION_FAILED'
        receipt['error'] = traceback.format_exc()
        print(receipt['error'], file=sys.stderr)
    finally:
        receipt['orchestration_wall_seconds'] = time.perf_counter()-t0
        receipt['code_wall_seconds'] = sum(x['wall_seconds'] for x in receipt['commands'])
        receipt['preparation_and_publication_excluded'] = True
        dump(OUT/'EXECUTION_RECEIPT.json', receipt)
        # Read source again to establish that the executed payload stayed frozen.
        unchanged = all(hashlib.sha256((WORK/name).read_bytes()).hexdigest() == expected
                        for name, expected in json.loads((HERE/'SOURCE_MANIFEST.json').read_text()).items()) if WORK.exists() else False
        dump(OUT/'SOURCE_READBACK.json', {'unchanged': unchanged})
        files = sorted(p for p in OUT.rglob('*') if p.is_file() and p.name != 'MANIFEST.sha256')
        (OUT/'MANIFEST.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(OUT).as_posix()+'\n' for p in files))
        print(json.dumps({'status': receipt['status'], 'code_wall_seconds': receipt['code_wall_seconds'], 'source_unchanged': unchanged}), flush=True)
    return exit_code

if __name__ == '__main__':
    raise SystemExit(main())
