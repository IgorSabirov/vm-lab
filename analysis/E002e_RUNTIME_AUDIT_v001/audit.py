"""Diagnostic repeat of one fixed algebra script; no G/R/F/T simulations."""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

OUT=Path(__file__).parent
ROOT=OUT.parents[1]
ORIGINAL=ROOT/'analysis/E002e_SMOKE_REVIEW_v001'
SOURCE=ORIGINAL/'checks.py'
SOURCE_SHA='ed7f14908ee5295bfb838c66a8a9493f46901318271b4f4f93c130dbcb71ddbe'
EXPECTED=6*.2529647119990841+.4+.08
LOWER,UPPER=1.1,3.5

def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def sha(p):return sha_bytes(p.read_bytes())

PROFILE_WRAPPER=r'''
import time
wrapper_start=time.perf_counter()
import ast,cProfile,json,os,pstats,resource,runpy,sys
from pathlib import Path
source=Path(sys.argv[1]);dest=Path(sys.argv[2]);dest.mkdir(parents=True,exist_ok=True)
before_load=time.perf_counter()
ns=runpy.run_path(str(source),run_name='__runtime_audit__')
after_load=time.perf_counter()
fn=ns['main'];fn.__globals__['OUT']=dest
counts={};filename=fn.__code__.co_filename
def trace(frame,event,arg):
    if frame.f_code.co_filename!=filename:return None
    if event=='line':counts[frame.f_lineno]=counts.get(frame.f_lineno,0)+1
    return trace
pr=cProfile.Profile();cpu0=time.process_time();before_main=time.perf_counter()
sys.settrace(trace);pr.enable()
try:fn()
finally:
    pr.disable();sys.settrace(None)
after_main=time.perf_counter();cpu1=time.process_time()
stats=pstats.Stats(pr)
top=[]
for (file,line,name),(cc,nc,tt,ct,callers) in sorted(stats.stats.items(),key=lambda x:x[1][3],reverse=True)[:30]:
    top.append(dict(file=file,line=line,name=name,primitive_calls=cc,total_calls=nc,self_seconds=tt,cumulative_seconds=ct))
assert_lines=[n.lineno for n in ast.walk(ast.parse(source.read_text())) if isinstance(n,ast.Assert)]
try:
    from threadpoolctl import threadpool_info
    pools=threadpool_info()
except ImportError:pools=None
report=dict(wrapper_setup_seconds=before_load-wrapper_start,script_load_and_imports_seconds=after_load-before_load,
    setup_between_load_and_main_seconds=before_main-after_load,main_instrumented_seconds=after_main-before_main,
    main_instrumented_cpu_seconds=cpu1-cpu0,line_executions={str(k):v for k,v in sorted(counts.items())},
    assert_line_executions={str(k):counts.get(k,0) for k in sorted(assert_lines)},
    profile_top_functions=top,python=sys.version,executable=sys.executable,optimize=sys.flags.optimize,
    numpy=sys.modules['numpy'].__version__,scipy=sys.modules['scipy'].__version__,threadpools=pools,
    peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
report['diagnostic_preparation_seconds']=time.perf_counter()-after_main
(dest/'profile.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
'''

def main():
    internal_start=time.perf_counter()
    original_files=[p for p in ORIGINAL.iterdir() if p.is_file()]
    original_hashes={p.name:sha(p) for p in original_files}
    assert sha(SOURCE)==SOURCE_SHA
    expected_output_sha=sha(ORIGINAL/'checks.json')
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    assert not env.get('PYTHONOPTIMIZE'), 'Assert optimisation must be explicitly reviewed'
    rows=[]
    with tempfile.TemporaryDirectory(prefix='e002e_runtime_audit_') as td:
        tmp=Path(td)
        for i in range(6):
            folder=tmp/f'plain_{i+1:02d}';folder.mkdir();copy=folder/'checks.py';shutil.copyfile(SOURCE,copy)
            assert sha(copy)==SOURCE_SHA
            cpu0=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
            r=subprocess.run(['python',str(copy)],capture_output=True,env=env)
            elapsed=time.perf_counter()-start;cpu1=resource.getrusage(resource.RUSAGE_CHILDREN)
            result=folder/'checks.json';result_sha=sha(result) if result.exists() else None
            row=dict(index=i+1,wall_seconds=elapsed,child_user_cpu_seconds=cpu1.ru_utime-cpu0.ru_utime,
                child_system_cpu_seconds=cpu1.ru_stime-cpu0.ru_stime,exit_code=r.returncode,
                output_file_sha256=result_sha,stdout_sha256=sha_bytes(r.stdout),stdout_bytes=len(r.stdout),stderr_bytes=len(r.stderr),
                source_sha256=sha(copy),result_identical=result_sha==expected_output_sha,
                provisional_range_status='IN_RANGE' if .15<=elapsed<=.40 else 'REVIEW_REQUIRED')
            rows.append(row)
            if r.returncode or not row['result_identical'] or r.stderr:
                raise RuntimeError(json.dumps(row)+'\n'+r.stderr.decode())
        wrapper=tmp/'profile_wrapper.py';wrapper.write_text(PROFILE_WRAPPER)
        folder=tmp/'profile';start=time.perf_counter()
        r=subprocess.run(['python',str(wrapper),str(SOURCE),str(folder)],capture_output=True,env=env)
        profile_wall=time.perf_counter()-start
        if r.returncode:raise RuntimeError(r.stderr.decode())
        profile=json.loads((folder/'profile.json').read_text())
        profile.update(full_child_wall_seconds=profile_wall,exit_code=r.returncode,
            result_identical=sha(folder/'checks.json')==expected_output_sha,
            stdout_sha256=sha_bytes(r.stdout),stdout_bytes=len(r.stdout),stderr_bytes=len(r.stderr),
            provisional_range_status='IN_RANGE' if .15<=profile_wall<=.90 else 'REVIEW_REQUIRED')
        assert profile['result_identical'] and all(n>0 for n in profile['assert_line_executions'].values())
    assert {p.name:sha(p) for p in original_files}==original_hashes
    times=[r['wall_seconds'] for r in rows]
    result=dict(status='REPLAY_CONTENT_VERIFIED',source_sha256=SOURCE_SHA,original_output_sha256=expected_output_sha,
        original_files_unchanged=True,original_files_sha256=original_hashes,
        current_environment=dict(python=sys.version,python_command=shutil.which('python'),platform=platform.platform(),
            inherited_PYTHONOPTIMIZE=os.environ.get('PYTHONOPTIMIZE'),override_OPENBLAS_NUM_THREADS='1',override_OMP_NUM_THREADS='1'),
        repeats=rows,repeat_summary=dict(count=len(times),mean=statistics.mean(times),median=statistics.median(times),
            min=min(times),max=max(times),sample_stdev=statistics.stdev(times)),profile=profile,
        internal_driver_seconds_to_report=time.perf_counter()-internal_start,
        diagnostic_forecast=dict(expected_seconds=EXPECTED,lower_seconds=LOWER,upper_seconds=UPPER),
        limitations=['Original phase times/version/threadpool/load/cache were not logged; new profile is not historical reconstruction',
                    'Fresh Python processes, OS file cache not cleared; no cold-machine claim',
                    'Instrumented main contains profiler and line-trace overhead',
                    'Original source has no full network NESS, spectra, or evolution'])
    (OUT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(repeats=result['repeat_summary'],profile_wall=profile_wall,
        profile_load=profile['script_load_and_imports_seconds'],profile_main=profile['main_instrumented_seconds'],
        all_content_identical=True,original_unchanged=True),indent=2))

if __name__=='__main__':main()
