"""Read-only follow-up to analyze_run.py; no simulation."""
import collections, json, sys
from pathlib import Path
root,out=map(Path,sys.argv[1:3]);a=json.loads((out/'CASES_RECOMPUTED.json').read_text())
names=[n for n in a if n.startswith('patch::long::') and n.endswith('::on')]
metrics=['final_function','consecutive_functional','mean_health']
cont={m:{'nonzero':sum(abs(a[n]['expected'][m]-a[n[:-2]+'off']['expected'][m])>1e-12 for n in names),
         'max_abs':max(abs(a[n]['expected'][m]-a[n[:-2]+'off']['expected'][m]) for n in names)} for m in metrics}
cont['compared_conditions']=len(names)
cont['identical_function_per_carrier']=sum(a[n]['function_per_carrier']==a[n[:-2]+'off']['function_per_carrier'] for n in names)
details={}
for n in ['patch::add_growing::full_base','patch::add_growing::G0::contact::on','patch::add_growing::G1::contact::on']:
    row=json.loads((root/'rows'/a[n]['file']).read_text())
    trace_path=root/'traces'/(row['task_id']+'.json');trace=json.loads(trace_path.read_text())
    events=[]
    for log in trace['log']:
        e=log.get('event',{})
        if e.get('owner')=='N2' and e.get('kind') in ['task_damage','task_restore','task_read','task_write','supply_arrive']:
            events.append(dict(kind=e['kind'],time=e['t'],before={k:log.get('before',{}).get(k) for k in ['fuel','precursor']},after={k:log.get('local',{}).get(k) for k in ['fuel','precursor']}))
    details[n]=dict(row='rows/'+a[n]['file'],trace='traces/'+trace_path.name,trace_input=trace['input_content'],events_N2=events,
        all_inputs=[dict(input=o['result']['input_content'],weight=o['weight'],tasks=o['result']['task_results']) for o in row['outcomes']])
repair=json.loads((out/'REPAIR_GRID.json').read_text());wave=json.loads((out/'WAVE_GRID.json').read_text())
groups=collections.defaultdict(list)
for r in repair:groups[(r['family'],r['generations'],r['delay'],r['damage'])].append(r)
geom=collections.Counter(json.loads(p.read_text()).get('status') for p in (root/'geometry').glob('*.json'))
measures={n:v['expected']['mean_task_success'] for n,v in a.items() if n.startswith('patch::') and (n.endswith('::independent') or (n.endswith('::full_base')))}
wave_index={(w['family'],w['modes'],w['detuning'],w['wait']):w for w in wave}
comparisons=[(w,wave_index[('add_quiet',w['modes'],w['detuning'],w['wait'])]) for w in wave if w['family']=='cdt_strip']
d=dict(continuation=cont,U001=details,geometry_status_counts=dict(geom),measure_task_probabilities=measures,
 final_task_positive=sum(r['q_task_final']>1e-12 for r in repair),eight_carrier_conditions=sum(r['generations']==8 for r in repair),
 eight_carrier_final_positive=sum(r['generations']==8 and r['q_task_final']>1e-12 for r in repair),
 fuel_plateau_192_288_384=sum(len({r['on'] for r in v if r['fuel']>=192})==1 for v in groups.values()),fuel_plateau_groups=len(groups),
 wave_cdt_quiet_max_difference=max(abs(x[k]-y[k]) for x,y in comparisons for k in ['dark','static']),wave_cdt_quiet_pairs=len(comparisons),
 sign_classification_tolerance=1e-12,analysis_scope='post-hoc read-only analysis; no new scientific run')
(out/'FOLLOWUP.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in d.items() if k!='U001'},ensure_ascii=False,indent=2))
