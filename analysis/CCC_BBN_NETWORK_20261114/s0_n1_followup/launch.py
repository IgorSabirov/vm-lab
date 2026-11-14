"""Explicit four-run follow-up. Reuse the validated N1 process/publication controller."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import common as c
import review

spec=importlib.util.spec_from_file_location('legacy_n1_launch',c.PKG.parent/'s0_n1/launch.py')
ctl=importlib.util.module_from_spec(spec);spec.loader.exec_module(ctl)

def preflight(root,up,committed=True):
    plan=c.read(c.PKG/'PLAN.json')
    if not plan['execution_enabled'] or not c.read(c.PKG/'RUN_REQUEST.json')['execution_enabled']:raise ValueError('Disabled request')
    if plan['numerical_budget']!=c.read(c.PARENT_ROOT/'N1_PREREGISTRATION.json')['numerical_budget']:raise ValueError('Changed numerical budgets')
    c.check_upstream(up)
    sys.path.insert(0,str(up))
    from primat.config import PRIMATConfig,DEFAULT_PARAMS
    from primat.cache_utils import fingerprint_hash
    from primat.weak_rates.cache import weak_rate_fingerprint,thermal_fingerprint
    configs={}
    for rid in ['PROBE']+[r['id'] for r in plan['runs']]:
        params=c.config_for(rid,root/'caches/BG8000');cfg=PRIMATConfig(params)
        c.validate_resolved({k:getattr(cfg,k) for k in DEFAULT_PARAMS},rid)
        if fingerprint_hash(weak_rate_fingerprint(cfg))!='dc55a0b9270e3e3d' or fingerprint_hash(thermal_fingerprint(cfg))!='cfdb4d324bb5651f':raise ValueError('Unexpected cache fingerprint')
        configs[rid]={**params,'cache_dir':'N1_CACHE/BG8000'}
    c.write(root/'RESOLVED_CONFIGS.json',configs)
    source=c.git('rev-parse','HEAD')
    inputs=[p for p in c.PKG.iterdir() if p.is_file() and p.name!='.gitignore']
    inputs+=[c.REPO/'.github/workflows/s0-n1-followup.yml']
    inputs+=[c.PKG.parent/'s0_n1'/n for n in ('launch.py','verify.py','worker.py','common.py')]
    inputs+=[c.REPO/p for p in c.read(c.PARENT_ROOT/'SOURCE_FREEZE.json')['files']]
    inputs+=[c.PARENT_ROOT/n for n in ('ARTIFACTS.json','ARTIFACTS_SHA256.json','CACHE_FREEZE.json','runs/R8/RESULT.json','runs/R8/MANIFEST.json','runs/PROBE/RESULT.json')]
    inputs+=list((c.PARENT_ROOT/'caches/BG8000').rglob('*.txt'))
    files={}
    for p in sorted(set(inputs)):
        rel=str(p.relative_to(c.REPO));files[rel]=c.digest(p)
        if committed and subprocess.check_output(['git','-C',str(c.REPO),'show',source+':'+rel])!=p.read_bytes():raise ValueError('Uncommitted frozen input: '+rel)
    c.write(root/'SOURCE_FREEZE.json',{'commit':source,'files':files,'scientific_acceptance':False})
    return plan

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--upstream',required=True);ap.add_argument('--static-check-only',action='store_true');a=ap.parse_args()
    up=Path(a.upstream).resolve()
    if a.static_check_only:
        with tempfile.TemporaryDirectory() as d:preflight(Path(d),up,False)
        print('Configuration/fingerprint checks PASS; no numerical integration');return 0
    req=c.read(c.PKG/'RUN_REQUEST.json')
    if req['id']!='S0_N1_FOLLOWUP_20261114_r1':raise ValueError('Unexpected request')
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!='IgorSabirov/vm-lab' or os.environ.get('GITHUB_REF')!='refs/heads/'+c.BRANCH or os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise ValueError('Wrong executor or forbidden retry')
    if c.git('rev-parse','HEAD')!=os.environ['GITHUB_SHA']:raise ValueError('Trigger SHA mismatch')
    root=c.PKG/'results'/req['id']
    if root.exists():raise ValueError('Existing request: no duplicate integration')
    root.mkdir(parents=True);start=time.monotonic();exit_code=1
    try:
        plan=preflight(root,up)
        evidence=review.analyze(root)
        e=c.env();signature=c.environment_signature(e)
        if (e['python'],e['numpy'],e['scipy'],e['threadpoolctl'])!=('3.12.16','2.3.5','1.17.0','3.6.0'):raise ValueError('Pinned dependency mismatch')
        if len(e['threadpools'])!=2 or any(p['num_threads']!=1 or p['internal_api']!='openblas' or p['version']!='0.3.30' for p in e['threadpools']):raise ValueError('Unexpected BLAS libraries')
        c.write(root/'ENVIRONMENT.json',e);c.write(root/'TARGET_ENVIRONMENT.json',{'signature':signature})
        ctl.append(root,{'kind':'AUTHORIZATION','request':req,'workflow_url':'https://github.com/IgorSabirov/vm-lab/actions/runs/'+os.environ['GITHUB_RUN_ID']})
        shutil.copytree(c.PARENT_ROOT/'caches/BG8000',root/'caches/BG8000')
        group=c.read(c.PARENT_ROOT/'CACHE_FREEZE.json')['groups']['BG8000']
        if c.snapshot(root/'caches/BG8000')!=group['overlay']:raise ValueError('Copied cache mismatch')
        c.write(root/'CACHE_FREEZE.json',{'groups':{'BG8000':group},'frozen_utc':c.now()})
        for p in (root/'caches').rglob('*'):
            if p.is_file():p.chmod(0o444)
        ctl.process(root,up,'PROBE',plan['runtime'],start)
        probe=c.read(root/'runs/PROBE/RESULT.json')
        oldprobe=c.read(c.PARENT_ROOT/'runs/PROBE/RESULT.json')
        strict=c.read(c.PARENT_ROOT/'runs/R8/RESULT.json')
        ratio=sum(x['solver_seconds'] for x in probe['eras'])/sum(x['solver_seconds'] for x in oldprobe['eras'])
        base=sum(x['solver_seconds'] for x in strict['eras'])*ratio
        factors={'F0':1.,'F_RATE':1.15,'F_ATOL':1.6,'F_REPEAT':1.}
        central={rid:base*f+probe['timing']['initialization_seconds']+10 for rid,f in factors.items()}
        prediction={'per_run_central':central,'seconds':{'low':.5*sum(central.values()),'central':sum(central.values()),'high':1.8*sum(central.values())},
                    'target_probe_seconds':probe['timing']['wall_seconds'],'target_to_parent_probe_solver_ratio':ratio,
                    'method':'Archived R8 per-era solver time scaled by fresh same-code coarse probe ratio; declared one-factor costs. 0.5–1.8 engineering envelope, not confidence interval.',
                    'preparation_seconds_used':ctl.spent(root),'historical_N1_seconds_not_recharged':c.read(c.PARENT_ROOT/'SUMMARY.json')['process_seconds']}
        c.write(root/'FORECAST.json',prediction);ctl.manifest(root);forecast_sha=ctl.publish(root)
        if prediction['seconds']['high']+time.monotonic()-start>plan['runtime']['package_cap_seconds'] or max(central.values())*1.8>plan['runtime']['process_cap_seconds']:raise ValueError('Target forecast exceeds declared hard caps')
        c.write(root/'ADMISSION.json',{'utc':c.now(),'forecast_commit':forecast_sha,'forecast_sha256':c.digest(root/'FORECAST.json')['sha256'],'strict_runs':list(factors),'scientific_acceptance':False})
        ctl.manifest(root);ctl.publish(root)
        for row in plan['runs']:
            ctl.process(root,up,row['id'],plan['runtime'],start);ctl.manifest(root);ctl.publish(root)
        import verify
        result=verify.analyze(root)
        actual=sum(e['wall_seconds'] for e in ctl.events(root) if e.get('kind')=='PROCESS' and e['run_id']!='PROBE')
        c.write(root/'SUMMARY.json',{'status':'ENGINEERING_PASS','numerical_status':result['status'],'executed_strict_runs':list(factors),'process_seconds':ctl.spent(root),'controller_seconds':time.monotonic()-start,
                    'runtime':{'forecast':prediction,'actual_strict_seconds':actual,'central_difference_seconds':actual-prediction['seconds']['central'],'within_envelope':prediction['seconds']['low']<=actual<=prediction['seconds']['high']},'scientific_acceptance':False})
        exit_code=0
    except Exception as exc:
        c.write(root/'EXECUTION_ERROR.json',{'utc':c.now(),'error':str(exc),'traceback':traceback.format_exc()});traceback.print_exc()
        c.write(root/'SUMMARY.json',{'status':'ENGINEERING_FAIL','numerical_status':'NOT_EVALUATED','error':str(exc),'scientific_acceptance':False})
    finally:
        ctl.manifest(root);ctl.publish(root)
    return exit_code

if __name__=='__main__':raise SystemExit(main())
