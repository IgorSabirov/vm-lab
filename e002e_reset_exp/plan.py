"""Frozen science, workload and fail-closed launch identity for RESET."""
import hashlib,json,os,re
from pathlib import Path
import numpy as np
from e002e_exp.runtime import ROOT,kernel_files,kernel_hash,compare_environment,memory_preflight
from e002e_exp.plan import selected_work,pinned_file
from e002e_corr_exp.plan import thread_preflight,storage_preflight

PROTOCOL=dict(version='E002e_RESET_v001',concept='E002e_RESET_v002',models=['QS','RR_QS'],
    gammas=[0.,.001,.002],primary='S_F_QS_POSITIVE',primary_branch='LU_WITH_OWN_FIXED_BASELINE_TARGET',
    dimensions=[8,27],q0_dimension=14580,reset_rank=20,epsilon=0.,phi_over_pi=.5,m6_v_over_J=1.,node_noise=.05,
    state_tolerance=1e-9,operator_tolerance=1e-10,small_signal_floor_S=1e-6,small_signal_floor_A=1e-6,
    guard_safety=10.,window_fraction=.20,linearity_fraction=.10,uncertainty_safety=3.,uncertainty_floor=1e-10,
    maximum_u_S=1e-6,maximum_u_delta_F=1e-8,conditional_floor=1e-6,
    calibration_seeds={'QS':192601,'RR_QS':192602},calibration_rhs_per_factor=1,
    calibration_wall_limit_seconds=180.,calibration_extra_factor_cases=[dict(model='QS',gamma=.002,method='gmres_ilu',
        rtol=1e-12,atol=1e-14,ilu_drop_tol=1e-6,ilu_fill_factor=15.)],
    excluded=['IC','new_epsilon','spectral_scan','tau_fit','physical_reset_rhs_in_calibration'])
SOLVERS=[dict(method='lu'),dict(method='gmres_ilu')]


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def protocol_hash():return hashlib.sha256(canonical(PROTOCOL).encode()).hexdigest()


def implementation_manifest():
    files=set(kernel_files())|set((ROOT/'e002e_reset_exp').glob('*.py'))
    files|={ROOT/'e002e_corr_exp'/name for name in ('__init__.py','core.py','environment.py','plan.py')}
    files|={ROOT/pkg/'__init__.py' for pkg in ('e002_exp','e002c_exp','e002d_exp')}
    files.add(ROOT/'experiments/e002e_reset/vm_entry.py')
    return [dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(files)]


def implementation_hash():return hashlib.sha256(canonical(implementation_manifest()).encode()).hexdigest()


def cases():
    result=[]
    for model in PROTOCOL['models']:
        rows=[c for c in selected_work('baseline')['full'] if c['model']==model and c['epsilon']==0
              and c['phi_over_pi']==.5 and c['node_noise']==.05 and c['m6_v_over_J']==1.]
        if len(rows)!=1:raise ValueError('Ambiguous baseline case')
        result.append(dict(rows[0],tasks=['NESS']))
    return result


def workload(mode):
    if mode=='production':return dict(NESS=12,response=4,random_rhs=0,factorizations=12,condition_estimates=6)
    if mode=='calibration':return dict(NESS=4,response=0,random_rhs=13,factorizations=13,condition_estimates=6)
    raise ValueError('Invalid mode')


def preflight(config,env,require_checkout=True):
    allowed={'mode','source_commit','protocol_sha256','implementation_sha256','technical_review','evidence',
             'calibration','forecast','memory_budget','science_freeze'}
    if set(config)-allowed:raise ValueError('Unsupported override')
    mode=config.get('mode');counts=workload(mode)
    if config.get('protocol_sha256')!=protocol_hash() or config.get('implementation_sha256')!=implementation_hash():
        raise ValueError('Implementation/protocol mismatch')
    if not re.fullmatch('[0-9a-f]{40}',config.get('source_commit','')) or (require_checkout and os.environ.get('VM_SOURCE_COMMIT')!=config['source_commit']):
        raise ValueError('Checkout identity mismatch')
    freeze=pinned_file(config['science_freeze'])
    if freeze.get('protocol_sha256')!=protocol_hash() or freeze.get('status')!='SCIENCE_FROZEN_BEFORE_NEW_PHYSICAL_RHS':
        raise ValueError('Science freeze missing')
    review=pinned_file(config['technical_review'])
    if review.get('status')!='REVIEWED_AND_CHECKED' or review.get('implementation_sha256')!=implementation_hash():
        raise ValueError('Current implementation not reviewed')
    evidence=pinned_file(config['evidence'])
    if evidence.get('protocol_sha256')!=protocol_hash():raise ValueError('Evidence protocol mismatch')
    records={}
    for item in evidence['cases']:
        baseline=pinned_file(item['baseline']);corr=pinned_file(item['corr'])
        cid=item['case_id']
        if cid in records or baseline['id']!=cid or corr['id']!=cid:raise ValueError('Duplicate/mismatched case evidence')
        if not baseline['quality']['pass'] or not baseline['refinement']['gate']['pass_gate']:raise ValueError('Invalid baseline evidence')
        records[cid]=dict(baseline=baseline,corr=corr)
    if set(records)!={c['id'] for c in cases()}:raise ValueError('Incomplete evidence')
    for case in cases():
        if any(records[case['id']]['baseline']['case'][k]!=case[k] for k in ('model','epsilon','phi_over_pi','node_noise','m6_v_over_J')):
            raise ValueError('Evidence physics mismatch')
        corr=records[case['id']]['corr']
        if any(corr['case'][k]!=case[k] for k in ('model','epsilon','phi_over_pi','node_noise','m6_v_over_J')):
            raise ValueError('CORR evidence physics mismatch')
        area=corr['result']['signed_area'];u=corr['result']['area_uncertainty']
        if not np.isfinite([area,u]).all() or u<0:raise ValueError('Invalid CORR area evidence')
    comparison=dict(comparable=False,reason='FIRST_BOUNDED_CALIBRATION')
    if mode=='production':
        cal=pinned_file(config['calibration'])
        if (cal.get('status')!='CALIBRATION_REVIEWED' or cal.get('counts')!=workload('calibration')
                or cal.get('implementation_sha256')!=implementation_hash() or cal.get('protocol_sha256')!=protocol_hash()
                or not re.fullmatch('[0-9a-f]{40}',cal.get('report_commit',''))):raise ValueError('Calibration identity mismatch')
        comparison=compare_environment(cal['environment'],env)
        if not comparison['comparable']:raise ValueError('Calibration environment changed')
        if config['forecast']!=cal['production_forecast'] or config['memory_budget']!=cal['memory_budget']:
            raise ValueError('Measured budget mismatch')
    f=config['forecast']
    if not all(np.isfinite(f[k]) for k in ('expected_seconds','lower_seconds','upper_seconds')) or not 0<f['lower_seconds']<=f['expected_seconds']<=f['upper_seconds']:
        raise ValueError('Invalid forecast')
    return dict(evidence=records,counts=counts,environment=comparison,threads=thread_preflight(env),
                memory=memory_preflight(config['memory_budget'],env))
