"""Offline reanalysis. No simulation or VM job is launched.
Usage: python analyze_run.py ARCHIVE_DIR CASES.json OUTPUT_DIR
"""
import collections, hashlib, json, math, statistics, sys
from pathlib import Path

root, cases_path, out = map(Path, sys.argv[1:4]); out.mkdir(parents=True,exist_ok=True)
def read(p): return json.loads(p.read_text())
def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def save(n,x): (out/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
idx=read(root/'ROWS_INDEX.json'); metrics=read(root/'METRICS.json'); definitions=read(cases_path)
four=read(root/'FOUR_CANDIDATE_RETURN.json')
bycase={}; errors=[]; masses=[]; modes=collections.Counter(); task_status=collections.Counter()
total_outcomes=0; balance_bad=0; unfinished=0; max_trace=0.; min_eig=0.; max_correction=0.
profile_fields=next(iter(metrics['contrasts'].values()))['profile_fields']
for i,p in enumerate(sorted((root/'rows').glob('*.json'))):
    row=read(p); modes[row['sampling_mode']]+=1
    if digest(row)!=idx['row_hashes'][i]:errors.append(['row_hash',i])
    if row['scientific_hash']!=idx['scientific_hashes'][i]:errors.append(['scientific_index',i])
    payload={k:v for k,v in row.items() if k not in set(row['task_descriptor'])|{'task_descriptor','task_id','task_compute_seconds','timing_scope','scientific_hash'}}
    if digest(payload)!=row['scientific_hash']:errors.append(['scientific_payload_hash',i])
    if row['sampling_mode']=='design_control':continue
    weighted=[(x['weight'],x['result']) for x in row['outcomes']] if 'outcomes' in row else [(1.,row['result'])]
    masses.append(abs(sum(w for w,r in weighted)-1)); total_outcomes+=len(weighted)
    name=row['case_id'];cfg=row['config'];n=cfg['generations']
    a=bycase.setdefault(name,dict(config=cfg,n_tasks=0,n_outcomes=0,expected=collections.defaultdict(float),profiles=collections.defaultdict(float),task_per_carrier=[0.]*n,function_per_carrier=[0.]*n,task_status={},file=p.name,compute_seconds=0.))
    a['n_tasks']+=1;a['n_outcomes']+=len(weighted);a['compute_seconds']+=row['task_compute_seconds']
    for w,r in weighted:
        balance_bad+=r['material_and_credit_balance']!=r['initial_totals'];unfinished+=not r['finished']
        for k,v in r.items():
            if isinstance(v,(int,float)) and not isinstance(v,bool): a['expected'][k]+=w*v
        key=json.dumps([{k:v.get(k) for k in profile_fields} for v in r['profile']],sort_keys=True,separators=(',',':'))
        a['profiles'][key]+=w
        for j,pr in enumerate(r['profile']):
            a['function_per_carrier'][j]+=w*pr['function']
            for q in pr.get('read_quality',{}).values():
                if isinstance(q,dict):
                    max_trace=max(max_trace,q.get('trace_error',0));min_eig=min(min_eig,q.get('min_eigenvalue',0));max_correction=max(max_correction,q.get('probability_correction_l1',0))
        for j,t in enumerate(r.get('task_results',[])):
            a['task_per_carrier'][j]+=w*t['success'];st=t.get('status','NOT_STARTED');a['task_status'][st]=a['task_status'].get(st,0)+w/n
            a['expected']['reserve_mass']+=w*bool(t.get('full_reserve'))/n
            a['expected']['reserve_success_joint']+=w*bool(t.get('full_reserve'))*t['success']/n
        a['expected']['blocked_routes']+=w*r.get('geometry',{}).get('blocked',0)

for a in bycase.values():
    nt=a['n_tasks']
    for key in ['expected','profiles','task_status']:
        a[key]={k:v/nt for k,v in a[key].items()}
    for key in ['task_per_carrier','function_per_carrier']:a[key]=[v/nt for v in a[key]]

scalar_map={'q_parent':'parent_function','q_child':'child_function','q_final':'final_function','mean_cycles':'consecutive_functional','mean_health':'mean_health','mean_spent_fuel':'total_spent_fuel','q_task_final':'final_task_success','q_task_mean':'mean_task_success'}
scalar_diffs=[];four_diffs=[];contrast_diffs=[];tv_diffs=[]
for name,s in metrics['summary'].items():
    a=bycase[name]
    for k,rk in scalar_map.items():
        if k in s and s[k] is not None:scalar_diffs.append(abs(s[k]-a['expected'][rk]))
    for j,g in enumerate(s['per_generation']):scalar_diffs.append(abs(g['p_function']-a['function_per_carrier'][j]))
    if name in four['cases']:
        f=four['cases'][name];e=a['expected']
        for k,rk in [('p_task_success','mean_task_success'),('p_full_fixed_reserve','reserve_mass'),('expected_credits','total_spent_fuel'),('expected_blocked_routes','blocked_routes')]:four_diffs.append(abs(f[k]-e[rk]))
        actual=None if e['reserve_mass']==0 else e['reserve_success_joint']/e['reserve_mass']
        if actual is None:
            if f['p_task_given_full_reserve'] is not None: errors.append(['reserve_null',name])
        else:four_diffs.append(abs(actual-f['p_task_given_full_reserve']))
contrasts=[]
for d in definitions['contrasts']:
    if d['id'] not in metrics['contrasts']:continue
    value=sum(w*bycase[n]['expected'][d.get('metric','final_function')] for w,n in zip(d['weights'],d['cases']))
    old=metrics['contrasts'][d['id']];contrast_diffs.append(abs(value-old['mean']))
    if len(d['cases'])==2:
        x,y=[bycase[n]['profiles'] for n in d['cases']];tv=sum(abs(x.get(k,0)-y.get(k,0)) for k in x.keys()|y.keys())/2
        tv_diffs.append(abs(tv-old['joint_profile_tv']))
    contrasts.append(dict(id=d['id'],cases=d['cases'],weights=d['weights'],metric=d.get('metric','final_function'),value=value))
for a in bycase.values():a.pop('profiles')
checks=dict(task_files=len(idx['row_hashes']),modes=dict(modes),outcomes=total_outcomes,cases=len(bycase),contrasts=len(contrasts),hash_errors=errors,
 max_probability_mass_error=max(masses),balance_failures=balance_bad,unfinished_outcomes=unfinished,
 max_summary_difference=max(scalar_diffs),max_patch_report_difference=max(four_diffs),max_contrast_difference=max(contrast_diffs),max_profile_tv_difference=max(tv_diffs),
 max_density_trace_error=max_trace,min_density_eigenvalue=min_eig,max_probability_correction=max_correction)
save('CHECKS.json',checks);save('CASES_RECOMPUTED.json',bycase);save('CONTRASTS_RECOMPUTED.json',contrasts)

def stats(v):
 return dict(n=len(v),positive=sum(x>1e-12 for x in v),zero=sum(abs(x)<=1e-12 for x in v),negative=sum(x< -1e-12 for x in v),minimum=min(v),maximum=max(v),median=statistics.median(v))
wave=[];repair=[]
for c in contrasts:
    name=c['id'];p=name.split('::')
    if name.startswith('wavegrid::'):
        wave.append(dict(id=name,family=p[1],modes=int(p[2][1:]),detuning=float(p[3][1:]),wait=int(p[4][1:]),difference=c['value'],dark=bycase[c['cases'][0]]['expected']['final_function'],static=bycase[c['cases'][1]]['expected']['final_function']))
    if name.startswith('patch::long::') and name.endswith('::on-off'):
        a=bycase[c['cases'][0]];cfg=a['config']; e=a['expected'];sham=name.rsplit('::',1)[0]+'::sham'
        repair.append(dict(id=name,family=p[2],generations=cfg['generations'],fuel=cfg['donor_fuel'],delay=cfg['supply_delay'],damage=cfg['task_damage'],on=e['mean_task_success'],off=bycase[c['cases'][1]]['expected']['mean_task_success'],sham=bycase[sham]['expected']['mean_task_success'],difference=c['value'],q_task_final=e['final_task_success'],q_final=e['final_function'],reserve=e['reserve_mass'],blocked=e['blocked_routes'],task_per_carrier=a['task_per_carrier'],function_per_carrier=a['function_per_carrier']))
save('WAVE_GRID.json',wave);save('REPAIR_GRID.json',repair)
summary=dict(wave=stats([w['difference'] for w in wave]),repair=stats([r['difference'] for r in repair]),wave_families={},repair_families={})
for f in sorted({w['family'] for w in wave}):
    summary['wave_families'][f]=stats([w['difference'] for w in wave if w['family']==f])
    vals=[r for r in repair if r['family']==f]
    summary['repair_families'][f]=dict(**stats([r['difference'] for r in vals]),positive_final_task=sum(r['q_task_final']>1e-12 for r in vals),max_final_task=max(r['q_task_final'] for r in vals))
summary['wave_by_modes']={str(m):stats([w['difference'] for w in wave if w['modes']==m]) for m in [16,32,64]}
summary['repair_by_delay']={str(d):stats([r['difference'] for r in repair if r['delay']==d]) for d in [0,16,64]}
summary['repair_by_damage']={d:stats([r['difference'] for r in repair if r['damage']==d]) for d in ['writer','contact']}
summary['ancestors']=dict(collections.Counter(r['status'] for r in read(root/'ANCESTOR_RETURN.json')))
save('SUMMARY.json',summary)
print(json.dumps(dict(checks=checks,summary=summary),ensure_ascii=False,indent=2))
