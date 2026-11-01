"""Rebuild pinned operators and recompute results from exported vectors; no solves."""
import hashlib,json
from pathlib import Path
import numpy as np
from e002_exp.model import maxabs
from e002e_exp.model import make_full
from e002e_exp.export import conditional_values
from e002e_exp.runtime import compare_environment,runtime_gate
from e002e_corr_exp.core import array_hash,physicality,marginals
from .core import Reset,analyze
from .certificates import state_record,uniqueness
from .plan import cases,workload,PROTOCOL,protocol_hash,implementation_hash,implementation_manifest,thread_preflight


def equal(a,b):
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if a is None or b is None or isinstance(a,bool) or isinstance(b,bool):return type(a)==type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return bool(np.isfinite([a,b]).all() and np.isclose(a,b,atol=1e-12,rtol=1e-11))
    return a==b


def vector(report,name):
    if not isinstance(name,str) or Path(name).name!=name:raise ValueError('Unsafe vector path')
    with np.load(report/name,allow_pickle=False) as a:
        if a.files!=['vector']:raise ValueError('Unexpected arrays')
        x=a['vector'].copy()
    if not np.isfinite(x).all():raise ValueError('Nonfinite vector')
    return x


def verify_case(report,rec,model,mode):
    space=model['space'];production=mode=='production';rows=rec['rows'];branches={};targets={};states={};responses={}
    expected={(m,g) for m in ('lu','gmres_ilu') for g in PROTOCOL['gammas']}
    actual=[(r['method'],r['gamma']) for r in rows if r['method']!='gmres_ilu_tight']
    if len(actual)!=len(expected) or set(actual)!=expected:raise ValueError('Case coverage mismatch')
    if sum(r['method']=='gmres_ilu_tight' for r in rows)!=(1 if not production and rec['model']=='QS' else 0):
        raise ValueError('Calibration extra-factor coverage mismatch')
    if not production:
        forbidden={'S','q_file','q_sha256','response','response_file','response_equation','response_sector','X_sha256'}
        if any(forbidden & set(b) for b in rec['branches'].values()) or any(forbidden & set(r) for r in rows):
            raise ValueError('Forbidden physical calibration fields')
        allowed={rec['model']+'_'+m+'_target.npz' for m in ('lu','gmres_ilu')}
        allowed|={r[k] for r in rows for k in ('state_file','random_rhs_file','random_solution_file') if k in r}
        if {p.name for p in report.glob(rec['model']+'_*.npz')}!=allowed:raise ValueError('Unexpected calibration arrays')
    for method in ('lu','gmres_ilu'):
        branch=rec['branches'][method];rho0=vector(report,next(r['state_file'] for r in rows if r['method']==method and r['gamma']==0))
        dims=(8,27) if space.d==216 else model['dimensions']
        tau=marginals(space.unpack(rho0),dims)[1];reset=Reset(space,tau,dims)
        targets[method]=tau;states[method]={}
        if maxabs(vector(report,rec['model']+'_'+method+'_target.npz')-tau)>1e-13:raise ValueError('Exported target differs')
        if array_hash(rho0)!=branch['rho0_sha256'] or array_hash(tau)!=branch['tau_sha256']:raise ValueError('Branch target identity mismatch')
        if not equal(reset.target,branch['target']):raise ValueError('Target physicality differs')
        values=dict(flux={})
        for row in (r for r in rows if r['method']==method):
            gamma=row['gamma']
            if not equal(row['reset'],reset.certificate):raise ValueError('Reset certificate mismatch')
            nsolves=int(gamma==0 or production)+int(not production or gamma==0)
            if row['solver']['counts']['task_solves']!=nsolves:raise ValueError('Internal solve count differs')
            if 'condition' in row and (not np.isfinite(row['condition']['value']) or row['condition']['value']<1):raise ValueError('Invalid condition estimate')
            def equation(x):return model['L']@x+gamma*(reset.apply(x)-x)
            if gamma==0 or production:
                x=vector(report,row['state_file'])
                states[method][gamma]=x
                if x.shape!=(space.size,) or maxabs(equation(x))>1e-9:raise ValueError('NESS equation failed')
                check=state_record(model,x,reset,gamma)
                if not equal(check,row['diagnostics']) or not equal(check['raw'],row['raw']):raise ValueError('State observables/certificates differ')
                values['flux'][str(gamma)]=check['raw']['F']
                if production:
                    other=next(r for r in rows if r['gamma']==gamma and r['method'] not in (method,'gmres_ilu_tight'))
                    errors={k:3*abs(row['raw'][k]-other['raw'][k]) for k in row['raw'] if not k.startswith('C_')}
                    if not equal(errors,row['primitive_uncertainty']) or not equal(conditional_values(row['raw'],errors),row['conditional']):
                        raise ValueError('Conditional metrics mismatch')
            if not production:
                if row.get('physical_reset_rhs_solved') is not False:raise ValueError('Calibration has physical reset solve')
                x=vector(report,row['random_solution_file']);b=vector(report,row['random_rhs_file'])
                from .task import random_rhs
                if maxabs(b-random_rhs(space,PROTOCOL['calibration_seeds'][rec['model']]))>1e-13:raise ValueError('Random RHS seed/distribution differs')
                if maxabs(equation(x)-b)>1e-9 or abs(space.trace(x))>1e-9 or abs(space.trace(b))>1e-11:
                    raise ValueError('Random calibration equation failed')
            elif gamma==0:
                q=reset.apply(rho0)-rho0;X=vector(report,branch['response_file'])
                responses[method]=X
                if (array_hash(q)!=branch['q_sha256'] or array_hash(X)!=branch['X_sha256']
                        or maxabs(vector(report,branch['q_file'])-q)>1e-13):raise ValueError('Response identity mismatch')
                if maxabs(model['L']@X+q)>1e-9 or abs(space.trace(X))>1e-9:raise ValueError('Response equation failed')
                xr=space.unpack(X)
                if maxabs(xr-xr.conj().T)>1e-9:raise ValueError('Response Hermiticity failed')
                values['S']=float((space.row(model['observables']['F'])@X).real)
        if not equal(values['flux'],branch['flux']) or (production and not equal(values['S'],branch['S'])):
            raise ValueError('Branch values mismatch')
        branches[method]=values
    if maxabs(targets['lu']-targets['gmres_ilu'])>1e-9:raise ValueError('Target discrepancy')
    if any(maxabs(states['lu'][g]-states['gmres_ilu'][g])>1e-9 for g in states['lu']):raise ValueError('State discrepancy')
    if production:
        if maxabs(responses['lu']-responses['gmres_ilu'])>1e-9:raise ValueError('Response discrepancy')
        result=analyze(branches['lu'],branches['gmres_ilu'],rec['area_reference'],rec['u_area'])
        if not equal(result,rec['result']):raise ValueError('Scientific verdict differs')
    else:
        if any('S' in b for b in rec['branches'].values()) or any('state_file' in r and r['gamma']!=0 for r in rows) or rec['result']['status']!='CALIBRATION_ONLY_NO_NEW_PHYSICAL_RESET_RHS':raise ValueError('Calibration leaks new physics')
        if rec['model']=='QS':
            row=next(r for r in rows if r['method']=='gmres_ilu_tight')
            rho0=vector(report,next(r['state_file'] for r in rows if r['method']=='lu' and r['gamma']==0))
            reset=Reset(space,marginals(space.unpack(rho0),dims)[1],dims)
            x=vector(report,row['random_solution_file']);b=vector(report,row['random_rhs_file'])
            ref=next(r for r in rows if r['method']=='lu' and r['gamma']==row['gamma'])
            if (maxabs(model['L']@x+row['gamma']*(reset.apply(x)-x)-b)>1e-9 or abs(space.trace(x))>1e-9
                or maxabs(x-vector(report,ref['random_solution_file']))>1e-8):raise ValueError('Tight random solve failed')
    return dict(status='VECTORS_OPERATORS_AND_DECISIONS_VERIFIED',model=rec['model'])


def verify_report(report,finalized=True):
    report=Path(report);load=lambda p:json.loads((report/p).read_text())
    manifest=load('manifest.json');paths=[e['path'] for e in manifest['files']]
    if len(paths)!=len(set(paths)) or set(paths)!={p.name for p in report.iterdir() if p.is_file() and p.name!='manifest.json'}:
        raise ValueError('Manifest coverage mismatch')
    for e in manifest['files']:
        if Path(e['path']).name!=e['path']:raise ValueError('Unsafe manifest path')
        data=(report/e['path']).read_bytes()
        if len(data)!=e['size'] or hashlib.sha256(data).hexdigest()!=e['sha256']:raise ValueError('Checksum mismatch')
    cfg=load('config.json');metrics=load('metrics.json');mode=cfg['mode']
    if load('status.json')['status']!='COMPLETED_NOT_ACCEPTED':raise ValueError('Failed/incomplete report')
    if (load('protocol.json')!=PROTOCOL or cfg['protocol_sha256']!=protocol_hash()
            or cfg['implementation_sha256']!=implementation_hash() or load('dependencies.json')!=implementation_manifest()):
        raise ValueError('Implementation/protocol provenance mismatch')
    before=load('environment_before.json');after=metrics['environment_after'];thread_preflight(before);thread_preflight(after)
    if not compare_environment(before,after)['comparable']:raise ValueError('Environment changed during run')
    if metrics['counts']!=workload(mode):raise ValueError('Workload mismatch')
    from .plan import preflight
    # preflight also revalidates pinned evidence, technical review and calibrated budgets.
    gate=preflight(cfg,before,require_checkout=False)
    if not equal(gate['environment'],load('preflight.json')['environment']):raise ValueError('Stored environment verdict differs')
    rt=metrics['runtime_gate'];expected=runtime_gate(cfg['forecast'],rt['actual_seconds'],workload(mode),metrics['counts'],gate['environment']['comparable'],mode=='production')
    if not equal(rt,expected):raise ValueError('Stored time verdict differs')
    out=[];records=[];count=dict.fromkeys(workload(mode),0)
    for case in cases():
        rec=load(case['model']+'_case.json')
        records.append(rec)
        if rec['case']!=case:raise ValueError('Case changed')
        original=gate['evidence'][case['id']]['corr']['result']
        if rec['area_reference']!=original['signed_area'] or rec['u_area']!=original['area_uncertainty']:raise ValueError('Area evidence changed')
        model=make_full(case)
        if not equal(uniqueness(model),load(case['model']+'_uniqueness_scope_v1.json')):raise ValueError('Uniqueness premises differ')
        baseline=gate['evidence'][case['id']]['baseline']['raw']
        for row in (r for r in rec['rows'] if r['gamma']==0):
            if any(abs(row['raw'][k]-baseline[k])>1e-8 for k in ('F','J_h','source','h6','P_m6_N2','inventory')):raise ValueError('Published baseline differs')
        out.append(verify_case(report,rec,model,mode))
        for row in rec['rows']:
            count['factorizations']+=1;count['NESS']+=int('state_file' in row)
            count['response']+=int('response' in row);count['random_rhs']+=int('random_solution_file' in row)
            count['condition_estimates']+=int('condition' in row)
    if count!=workload(mode):raise ValueError('Actual exported workload differs')
    if finalized and mode=='calibration':
        from .budget import forecast
        if not equal(load('calibration.json'),forecast(cfg,metrics,records,before)):raise ValueError('Calibration budget differs')
        peak=after['process_peak_vm_bytes'];rss=after['process_peak_rss_bytes']
        if peak<after['process_vm_size_bytes'] or rss<=0 or peak>=after['address_space_rlimit'][0]:raise ValueError('Invalid memory high-water record')
    return dict(status='VERIFIED',cases=out,counts=count,full_archive_access=False)
