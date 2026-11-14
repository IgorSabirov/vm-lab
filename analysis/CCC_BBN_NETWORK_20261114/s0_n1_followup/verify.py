"""Read-only follow-up analysis; all budgets inherited unchanged from N1."""
import importlib.util
from pathlib import Path
import numpy as np
import common as c

spec=importlib.util.spec_from_file_location('legacy_n1_verify',c.PKG.parent/'s0_n1/verify.py')
legacy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)

def compare(a,b,plan):
    out={}
    for key in a:
        bound,kind=legacy.budget_for(key,plan)
        d=legacy.delta(a[key],b[key])
        out[key]={**d,'limit':bound,'metric':kind,'pass':d[kind]<=bound}
    return out

def analyze(root):
    root=Path(root);c.verify_freeze(root);verified=c.verify_artifacts(root)
    plan=c.read(c.PKG/'PLAN.json');runs={};values={};baryons={}
    frozen=c.read(root/'CACHE_FREEZE.json')['groups']['BG8000']
    target=c.read(root/'TARGET_ENVIRONMENT.json')['signature']
    for row in plan['runs']:
        rid=row['id'];r,t,raw,m=legacy.read_run(root,rid)
        if r['status']!='ENGINEERING_PASS':raise ValueError('Incomplete run '+rid)
        if m['config']!=c.read(root/'RESOLVED_CONFIGS.json')[rid]:raise ValueError('Configuration mismatch')
        if m['atol_scale']!=row['atol_scale']:raise ValueError('atol declaration mismatch')
        if m['source_commit']!=c.read(root/'SOURCE_FREEZE.json')['commit'] or m['upstream_commit']!=c.PIN:raise ValueError('Source mismatch')
        if c.environment_signature(m['environment'])!=target:raise ValueError('Environment mismatch')
        if r['cache_before']!=frozen['overlay'] or r['cache_after']!=frozen['overlay']:raise ValueError('Cache changed')
        for info in frozen['weak_files'].values():
            if r['loaded_files'].get(info['source'])!=info['identity']:raise ValueError('Unexpected weak table loaded')
        for era in r['eras']:
            name=era['era'];rt=row['numerical_precision']*(10 if name=='LT' else 1)
            at={'HT':1e-10,'MT':1e-15,'LT':1e-26}[name]*row['atol_scale']
            if era['rtol']!=rt or era['atol']!=at:raise ValueError('Effective tolerance mismatch')
        expected={e:m['network'][e] for e in ('HT','MT','LT')}
        baryons[rid]=legacy.baryon(rid,r,raw,m['mass_numbers'],expected)
        values[rid]=legacy.scalar_values(r);runs[rid]=(r,t,raw,m)
    first,last=runs['F0'],runs['F_REPEAT']
    repeat={'all_raw_arrays_equal':all(np.array_equal(first[2][k],last[2][k]) for k in first[2]),
            'temperature_traces_equal':first[1]==last[1],
            'reported_outputs_equal':first[0]['result']==last[0]['result']}
    repeat['pass']=all(repeat.values())
    gates={rid:compare(values[rid],values['F0'],plan) for rid in ('F_RATE','F_ATOL')}
    stable=all(g['pass'] for v in gates.values() for g in v.values())
    parent=legacy.scalar_values(c.read(c.PARENT_ROOT/'runs/R8/RESULT.json'))
    env=compare(values['F0'],parent,plan)
    env_ok=all(g['pass'] for g in env.values())
    result={'status':'OPERATING_POINT_STABILITY_PASS' if stable and repeat['pass'] and env_ok else 'OPERATING_POINT_REVIEW_REQUIRED',
            'engineering_status':'ENGINEERING_PASS','repeat':repeat,'refinement_gates':gates,
            'environment_comparison_to_archived_R8':env,'observables':values,'artifact_hashes_verified':verified,
            'original_N1_status':'NUMERICAL_CONVERGENCE_FAIL_UNCHANGED',
            'scope':'Only the declared rate-grid/atol perturbations and before/after process replay at the R8 point. No all-parameter convergence theorem, observational likelihood or S2 signal.',
            'recommended_reference':'F0/R8 configuration if all declared checks pass; preserve F_RATE/F_ATOL outputs as sensitivity evidence',
            'scientific_acceptance':False}
    c.write(root/'FOLLOWUP_SUMMARY.json',result);c.write(root/'BARYON_BUDGET.json',baryons)
    lines=['# S0-N1 targeted follow-up','',f"Engineering: **ENGINEERING_PASS**. Result: **{result['status']}**.",'',
           f"Fresh-process replay: **{'PASS' if repeat['pass'] else 'FAIL'}**. Original N1 FAIL is retained.",'',
           '| Run | Yp | D/H | Neff | Final neutron abundance |','|---|---:|---:|---:|---:|']
    for rid,v in values.items():lines.append(f"| {rid} | {v['YPBBN']:.16g} | {v['DoH']:.16g} | {v['Neff']:.16g} | {v['Y_n']:.16g} |")
    lines+=['','All original numerical budgets retained. Only this declared operating-point stability claim is assessed. The historical coarse-grid comparison is not rewritten.','',result['scope']]
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return result
