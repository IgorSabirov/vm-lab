"""One admission, independent sections without duration deadlines, integrity + independent domain checks.

This installed executor is local/sequential. Other routes fail before execution;
execution_policy still describes the broader architecture, not a deployed worker.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

from infra.autonomy.execution_policy import validate, digest
from infra.run_contract import validate_plan, verify_receipt, canonical_hash
from infra.adapters.domain_verify import verify

ALLOWED = {'add_f2', 'serbian_signature'}


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def files(folder):
    return [{'path': str(p.relative_to(folder)), 'size_bytes': p.stat().st_size,
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(folder.rglob('*')) if p.is_file() and p != folder/'RESULT_MANIFEST.json' and 'build' not in p.relative_to(folder).parts]


def validate_package(plan, root, limits):
    result = validate(plan, limits, root=root)
    if result['executor'] != 'local' or result['parallel_sections'] != 1:
        raise ValueError('Installed package runner supports local sequential sections only')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if head != plan['source_commit']:
        raise ValueError('Checkout must be exactly the frozen source commit')
    if subprocess.check_output(['git', 'diff', 'HEAD', '--name-only'], cwd=root, text=True).strip():
        raise ValueError('Tracked source changed after freeze')
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=root, text=True).strip()
    run_ids = set()
    for section in plan['sections']:
        rp = section['run_plan']; validate_plan(rp)
        if rp['run_id'] in run_ids: raise ValueError('Duplicate section run identity')
        run_ids.add(rp['run_id'])
        if section['adapter'] not in ALLOWED or rp['command']['entrypoint'] != 'infra/adapters/worker.py':
            raise ValueError('Adapter/entrypoint is not allowlisted')
        if len(section['task_ids']) != 1 or rp['source']['commit'] != head or rp['source']['tree_sha'] != tree:
            raise ValueError('Section source/task mismatch')
        if rp['source']['config_sha256'] != canonical_hash(section['config']):
            raise ValueError('Section config differs from frozen plan')
        if rp['source']['input_manifest_sha256'] != plan['input_manifest']['sha256']:
            raise ValueError('Section input manifest mismatch')
        if (rp['budget']['memory_limit_mib']*1024**2 > section['memory_bytes'] or
            rp['budget']['disk_limit_mib']*1024**2 > plan['budget']['output_bytes']):
            raise ValueError('Section receipt budget exceeds package reservation')
    return result


def check_admission(plan, admission):
    row = admission.get('reservation', {})
    if (admission.get('admitted') is not True or row.get('status') != 'RESERVED' or
        row.get('id') != plan['package_id'] or row.get('source_sha') != plan['source_commit'] or
        row.get('execution_plan_sha256') != digest(plan) or row.get('executor') != 'local' or
        not admission.get('ledger_blob_sha')):
        raise ValueError('Missing read-back of the single package reservation')


def bounded(command, folder, env, seconds, memory, disk, package_out):
    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_FSIZE, (disk, disk))
    start = time.monotonic(); peak = 0
    with (folder/'stdout.log').open('wb') as log:
        child = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, preexec_fn=limits)
        try:
            while child.poll() is None:
                rss = 0
                for stat in Path('/proc').glob('[0-9]*/stat'):
                    try:
                        data = stat.read_text().rsplit(')', 1)[1].split()
                        if int(data[2]) == child.pid:
                            rss += int(data[21])*os.sysconf('SC_PAGE_SIZE')
                    except (OSError, ValueError, IndexError):
                        continue
                peak = max(peak, rss)
                size = sum(p.stat().st_size for p in package_out.rglob('*') if p.is_file())
                if rss > memory or size > disk:
                    raise RuntimeError('Section/package resource budget exceeded')
                time.sleep(.05)
            if child.returncode:
                raise RuntimeError(f'Adapter exited {child.returncode}; preserve stdout.log')
        finally:
            # No orphaned compiler/worker may survive release of the lease.
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait()
    return {'seconds': time.monotonic()-start, 'peak_group_rss_bytes': peak, 'returncode': child.returncode}


def execute_sections(plan, root, output, admission=None):
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic(); summary = {'package_id': plan['package_id'], 'source_sha': plan['source_commit'],
        'plan_sha256': digest(plan), 'sections': [], 'scientific_acceptance': False,
        'excluded_reproducible_scratch': ['*/build/'],
        'preserved_evidence': 'RAW, DOMAIN, BUILD report, PROCESS, stdout and section plans; build source is pinned'}
    dump(output/'EXECUTION_PLAN.json', plan)
    if admission is not None: dump(output/'ADMISSION.json', admission)
    for section in plan['sections']:
        folder = output/section['id']; folder.mkdir(); rp = section['run_plan']
        dump(folder/'SECTION.json', section)
        process = {'run_id': rp['run_id'], 'source_commit': plan['source_commit'],
                   'state': 'FAILED', 'technical_gate': 'REVIEW_REQUIRED', 'scientific_confirmation': False}
        try:
            env = dict(os.environ, PYTHONPATH=str(root), SOURCE_ROOT=str(root),
                       SECTION_PLAN=str(folder/'SECTION.json'), SECTION_OUTPUT=str(folder),
                       OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
            process.update(bounded([sys.executable, '-m', 'infra.adapters.worker'], folder, env, None,
                                   section['memory_bytes'], plan['budget']['output_bytes'], output))
            raw = json.loads((folder/'RAW.json').read_text())
            check = verify(section['adapter'], raw, section['config']); dump(folder/'DOMAIN.json', check)
            process.update(state='COMPLETED', technical_gate='PASS')
        except Exception as exc:
            process['error'] = type(exc).__name__+': '+str(exc)
            if not (folder/'DOMAIN.json').exists():
                dump(folder/'DOMAIN.json', {'status':'REVIEW_REQUIRED', 'error':process['error']})
        dump(folder/'PROCESS.json', process)
        # Failure still gets a manifest; missing RAW is an integrity REVIEW, never a retry.
        dump(folder/'RESULT_MANIFEST.json', {'run_id':rp['run_id'], 'source_commit':plan['source_commit'],
             'plan_sha256':canonical_hash(rp), 'files':files(folder)})
        try: integrity = verify_receipt(folder, rp)
        except Exception as exc: integrity = {'integrity':'REVIEW_REQUIRED', 'error':str(exc)}
        summary['sections'].append({'id':section['id'], 'process':process, 'integrity':integrity})
        dump(output/'SUMMARY.json', summary)
        # Sections here are preregistered independent tasks; no dependent stage is launched.
    summary.update(seconds=time.monotonic()-start,
                   engineering='PASS' if all(s['process']['technical_gate']=='PASS' and
                     s['integrity']['integrity']=='PASS' for s in summary['sections']) else 'REVIEW_REQUIRED')
    forecast = sum(t['forecast_seconds'] for t in plan['tasks']) + sum(
        s[k] for s in plan['sections'] for k in ('setup_seconds','verification_seconds','publication_seconds'))
    summary['runtime_gate'] = {'forecast_seconds': forecast, 'actual_seconds': summary['seconds'],
                               'actual_over_forecast': summary['seconds']/forecast, 'duration_limit_seconds': None}
    dump(output/'SUMMARY.json', summary)
    dump(output/'ARTIFACTS.json', {'files':files(output), 'scientific_acceptance':False})
    return summary


def main():
    ap=argparse.ArgumentParser();ap.add_argument('plan', type=Path);ap.add_argument('--admission',type=Path)
    ap.add_argument('--output',type=Path);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    root=Path(__file__).resolve().parents[1]; plan=json.loads(a.plan.read_text())
    report=validate_package(plan,root,json.loads((root/'infra/autonomy/CONTROL.json').read_text())['limits'])
    if a.execute:
        if a.admission is None or a.output is None: raise ValueError('Admission and new output directory required')
        admission=json.loads(a.admission.read_text());check_admission(plan,admission)
        report=execute_sections(plan,root,a.output.resolve(),admission)
    print(json.dumps(report))
    if report.get('engineering') == 'REVIEW_REQUIRED': raise SystemExit(1)


if __name__=='__main__': main()
