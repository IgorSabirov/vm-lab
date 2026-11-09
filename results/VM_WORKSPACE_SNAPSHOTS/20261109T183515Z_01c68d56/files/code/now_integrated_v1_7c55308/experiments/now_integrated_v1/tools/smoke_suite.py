#!/usr/bin/env python3
"""Run bounded integration smoke and real subprocess recovery probes after review."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
from nowexp.provenance import atomic_json, read_json, verify_source, digest, environment


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--source-manifest',required=True)
    parser.add_argument('--acceptance',required=True)
    parser.add_argument('--signature-library',type=Path)
    args=parser.parse_args()
    files=verify_source(ROOT,args.source_commit,args.source_manifest)
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    checks=[]
    atomic_json(output/'ENVIRONMENT.json',environment())
    base=[sys.executable,str(ROOT/'run.py'),'--phase','smoke','--source-commit',args.source_commit,
          '--source-manifest',str(Path(args.source_manifest).resolve()),'--acceptance',str(Path(args.acceptance).resolve())]

    if args.signature_library is not None:
        base += ['--signature-library', str(args.signature_library.resolve())]

    def invoke(name,command,expected=0):
        remaining=600-(time.monotonic()-start)
        if remaining <= 0:raise TimeoutError('entire smoke suite wall cap')
        before=time.monotonic()
        with (output/(name+'.log')).open('w') as log:
            process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                code=process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.terminate()  # supervisor forwards termination to the actual worker
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                raise
        ok=(code==expected) if expected is not None else code!=0
        checks.append(dict(name=name,passed=ok,returncode=code,seconds=time.monotonic()-before))
        if not ok:raise AssertionError(name+' failed; see '+str(output/(name+'.log')))

    def hashes(directory):
        return read_json(directory/'ROWS_INDEX.json')['scientific_hashes']

    try:
        invoke('unit_tests',[sys.executable,'-m','unittest','discover','-s','tests','-v'])
        baseline=output/'baseline'
        invoke('full_smoke',base+['--output',str(baseline)])
        reference=hashes(baseline)
        for point in ('after_row','after_checkpoint','finalization'):
            directory=output/point
            invoke(point+'_crash',base+['--output',str(directory),'--fault',point],86)
            invoke(point+'_resume',base+['--output',str(directory),'--resume'])
            same=hashes(directory)==reference
            checks.append(dict(name=point+'_scientific_equality',passed=same))
            if not same:raise AssertionError('resumed output differs at '+point)
            if read_json(directory/'STATUS.json')['state']!='COMPLETED':raise AssertionError('stale failure state')
        # Actual SIGTERM of the supervisor after a durable late checkpoint.
        directory=output/'user_stop'
        with (output/'user_stop.log').open('w') as log:
            process=subprocess.Popen(base+['--output',str(directory),'--fault','hang'],cwd=ROOT,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                while not (directory/'FAULT_READY.json').exists():
                    if process.poll() is not None:raise AssertionError('stop probe ended before late checkpoint')
                    if time.monotonic()-start>570:raise TimeoutError('stop probe')
                    time.sleep(.05)
                process.terminate()
                process.wait(timeout=5)
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=5)
        stopped=read_json(directory/'STATUS.json')['reason']=='USER_INTERRUPT'
        checks.append(dict(name='late_user_interrupt',passed=stopped))
        if not stopped:raise AssertionError('user interrupt not recorded')
        invoke('user_stop_resume',base+['--output',str(directory),'--resume'])
        if hashes(directory)!=reference:raise AssertionError('user stop resume differs')
        checks.append(dict(name='user_stop_scientific_equality',passed=True))
        # Force a hang immediately, under a shortened diagnostic-only wall cap.
        directory=output/'watchdog'
        invoke('hard_wall',base+['--output',str(directory),'--fault','hang','--fault-fraction','0.001','--diagnostic-wall-cap','2'],None)
        bounded=read_json(directory/'STATUS.json')['reason']=='HARD_WALL_LIMIT'
        checks.append(dict(name='external_watchdog_killed_hang',passed=bounded))
        if not bounded:raise AssertionError('watchdog reason mismatch')
        # A corrupted committed result must be rejected, never silently recomputed.
        directory=output/'tampered'
        shutil.copytree(baseline,directory)
        row=read_json(directory/'rows/000000.json')
        row['scientific_hash']='tampered'
        atomic_json(directory/'rows/000000.json',row)
        invoke('tampered_row_rejected',base+['--output',str(directory),'--resume'],None)
        if read_json(directory/'RUN.json').get('complete'):raise AssertionError('tamper left completed status')
        wrong=base.copy()
        wrong[wrong.index('--source-commit')+1]='0'*40
        invoke('wrong_commit_rejected',wrong+['--output',str(output/'wrong_commit')],None)
        report=dict(schema=1,status='PASSED',phase='smoke',complete=True,technical_pass=True,
                    source_commit=args.source_commit,source_digest=digest(files),checks=checks,
                    wall_seconds=time.monotonic()-start,hard_wall_seconds=600,
                    forecast_status='FIRST_BOUNDED_SANDBOX_MEASUREMENT_NOT_VM_FORECAST',
                    scientific_confirmation=False,baseline_report=str(baseline/'RUN.json'))
        atomic_json(output/'SMOKE_SUITE.json',report)
        print(json.dumps(report,ensure_ascii=False))
    except BaseException as exc:
        atomic_json(output/'SMOKE_SUITE.json',dict(status='FAILED',phase='smoke',complete=False,technical_pass=False,
            source_commit=args.source_commit,source_digest=digest(files),checks=checks,
            wall_seconds=time.monotonic()-start,error=type(exc).__name__+': '+str(exc)))
        raise


if __name__=='__main__':main()
