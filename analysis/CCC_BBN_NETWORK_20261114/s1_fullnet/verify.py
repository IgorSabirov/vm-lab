"""Verify the conditional S1 claim and deliberately broken cooling-only control."""
import importlib.util
from pathlib import Path
import numpy as np
import common as c

spec=importlib.util.spec_from_file_location('n1_verify',c.PKG.parent/'s0_n1/verify.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)

def aligned(a,b):
    if [x['era'] for x in a['eras']]!=['HT','MT','LT'] or len(b['eras'])!=3:raise ValueError('Missing eras')
    for x,y in zip(a['eras'],b['eras']):
        if x['era']!=y['era'] or x['species']!=y['species'] or x['T_MeV']!=y['T_MeV']:raise ValueError('Misaligned temperature/species grids')
        if np.asarray(x['Y']).shape!=(401,len(x['species'])) or np.asarray(y['Y']).shape!=(401,len(y['species'])):raise ValueError('Trace shape mismatch')
        if not np.isfinite(x['Y']).all() or not np.isfinite(y['Y']).all():raise ValueError('Nonfinite trace')

def make_envelope():
    paths={rid:c.REFERENCE_ROOT/'runs'/rid/'TRACE.json' for rid in ('F0','F_RATE','F_ATOL')}
    traces={rid:c.read(path) for rid,path in paths.items()}
    for rid in ('F_RATE','F_ATOL'):aligned(traces['F0'],traces[rid])
    eras=[]
    for k,b in enumerate(traces['F0']['eras']):
        y=np.asarray(b['Y']);d=np.maximum(np.max(abs(np.asarray(traces['F_RATE']['eras'][k]['Y'])-y),axis=0),np.max(abs(np.asarray(traces['F_ATOL']['eras'][k]['Y'])-y),axis=0))
        tol=5*d+1e-10*np.max(abs(y),axis=0)+1e-14
        eras.append({'era':b['era'],'species':b['species'],'absolute_tolerance':tol.tolist(),'max_refinement_difference':d.tolist()})
    return {'formula':c.read(c.PKG/'PLAN.json')['trajectory_envelope']['formula'],'sources':{rid:c.digest(path) for rid,path in paths.items()},'eras':eras,'scientific_acceptance':False}

def trace_compare(base,other,envelope):
    aligned(base,other);rows=[]
    for b,x,e in zip(base['eras'],other['eras'],envelope['eras']):
        if e['era']!=b['era'] or e['species']!=b['species']:raise ValueError('Envelope mismatch')
        delta=np.max(abs(np.asarray(x['Y'])-np.asarray(b['Y'])),axis=0);tol=np.asarray(e['absolute_tolerance'])
        if not np.isfinite(tol).all() or np.any(tol<=0):raise ValueError('Invalid envelope')
        rows.append({'era':b['era'],'species':b['species'],'max_absolute_difference':delta.tolist(),'tolerance':tol.tolist(),'max_ratio':float(np.max(delta/tol)),'pass':bool(np.all(delta<=tol))})
    return {'eras':rows,'pass':all(r['pass'] for r in rows),'max_ratio':max(r['max_ratio'] for r in rows)}

def scalar_compare(a,b,plan):
    out={}
    for k in a:
        bound,kind=legacy.budget_for(k,plan);d=legacy.delta(a[k],b[k])
        out[k]={**d,'limit':bound,'metric':kind,'ratio':d[kind]/bound,'pass':d[kind]<=bound}
    return out

def analyze(root):
    root=Path(root);c.verify_freeze(root);count=c.verify_artifacts(root);plan=c.read(c.PKG/'PLAN.json')
    envelope=c.read(c.PKG/'ENVELOPE.json')
    if envelope!=make_envelope():raise ValueError('Frozen S0 envelope differs from its archived inputs')
    runs={};values={};baryons={};cache=c.read(root/'CACHE_FREEZE.json')['groups']['BG8000'];target=c.read(root/'TARGET_ENVIRONMENT.json')['signature']
    for row in plan['runs']:
        rid=row['id'];r,t,raw,m=legacy.read_run(root,rid)
        if r['status']!='ENGINEERING_PASS' or m['config']!=c.read(root/'RESOLVED_CONFIGS.json')[rid]:raise ValueError('Run/config mismatch')
        if m['mode']!=row['mode'] or m['clock']!={'f0':row['f0'],'alpha_s_inv':row['alpha_s_inv']}:raise ValueError('Clock mismatch')
        if m['source_commit']!=c.read(root/'SOURCE_FREEZE.json')['commit'] or m['upstream_commit']!=c.PIN:raise ValueError('Source mismatch')
        if c.environment_signature(m['environment'])!=target:raise ValueError('Environment mismatch')
        if r['cache_before']!=cache['overlay'] or r['cache_after']!=cache['overlay']:raise ValueError('Cache mutation')
        for info in cache['weak_files'].values():
            if r['loaded_files'].get(info['source'])!=info['identity']:raise ValueError('Wrong weak table loaded')
        if not all(v>0 for v in r['kernel_calls'].values()):raise ValueError('Unobserved kernel path')
        if row['mode']!='S0' and not r['clock_audit']:raise ValueError('Missing clock audit')
        for era in r['eras']:
            name=era['era']
            if era['rtol']!=row['numerical_precision']*(10 if name=='LT' else 1) or era['atol']!={'HT':1e-10,'MT':1e-15,'LT':1e-26}[name]:raise ValueError('Tolerance mismatch')
        expected={e:m['network'][e] for e in ('HT','MT','LT')}
        if len(expected['LT'])!=59 or len(m['network']['LT_channels'])!=428:raise ValueError('Incomplete full network')
        baryons[rid]=legacy.baryon(rid,r,raw,m['mass_numbers'],expected);values[rid]=legacy.scalar_values(r);runs[rid]=(r,t,raw,m)
    archived=legacy.scalar_values(c.read(c.REFERENCE_ROOT/'runs/F0/RESULT.json'))
    control_scalars=scalar_compare(values['CONTROL'],archived,plan)
    control_trace=trace_compare(c.read(c.REFERENCE_ROOT/'runs/F0/TRACE.json'),runs['CONTROL'][1],envelope)
    positive_scalars=scalar_compare(values['S1'],values['CONTROL'],plan)
    positive_trace=trace_compare(runs['CONTROL'][1],runs['S1'][1],envelope)
    negative_scalars=scalar_compare(values['NEGATIVE'],values['CONTROL'],plan)
    negative_trace=trace_compare(runs['CONTROL'][1],runs['NEGATIVE'][1],envelope)
    control_ok=all(v['pass'] for v in control_scalars.values()) and control_trace['pass']
    positive_ok=all(v['pass'] for v in positive_scalars.values()) and positive_trace['pass']
    negative_ok=negative_trace['max_ratio']>=100 and max(negative_scalars[k]['ratio'] for k in ('YPBBN','DoH'))>=100
    out={'status':'CONDITIONAL_INVARIANCE_PASS' if control_ok and positive_ok and negative_ok else 'CONDITIONAL_INVARIANCE_REVIEW_REQUIRED',
         'engineering_status':'ENGINEERING_PASS','control_pass':control_ok,'positive_invariance_pass':positive_ok,'negative_control_detected':negative_ok,
         'observables':values,'control_scalars':control_scalars,'positive_scalars':positive_scalars,'negative_scalars':negative_scalars,
         'control_trajectory':control_trace,'positive_trajectory':positive_trace,'negative_trajectory':negative_trace,
         'artifact_hashes_verified':count,'envelope_sha256':c.digest(c.PKG/'ENVELOPE.json')['sha256'],
         'claim':'Y_i(T) is invariant within the declared numerical contract when the full reaction dynamics and cooling share the prescribed common clock. Cooling-only breaks that invariance.',
         'limitations':['Conditional reparametrization, not a derivation of CCC microphysics','Physical clock identification is not established','Tiny trace species below the absolute trajectory floor have no relative-accuracy certificate','Neutrino history and dimensionless inputs fixed; S2 and observational likelihood not tested'],
         'scientific_acceptance':False}
    c.write(root/'S1_SUMMARY.json',out);c.write(root/'BARYON_BUDGET.json',baryons)
    lines=['# Full-network conditional S1','',f"Result: **{out['status']}**. Engineering: **ENGINEERING_PASS**.",'',
           '| Run | Yp | D/H | Neff |','|---|---:|---:|---:|']
    for rid,v in values.items():lines.append(f"| {rid} | {v['YPBBN']:.16g} | {v['DoH']:.16g} | {v['Neff']:.16g} |")
    lines+=['',f"Matched control: {control_ok}; common-clock invariance: {positive_ok}; cooling-only control detected: {negative_ok}.",'',out['claim'],'']+['- '+x for x in out['limitations']]
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n');return out
