#!/usr/bin/env python3
"""Offline arithmetic on saved GitHub artifacts; no simulator imports or VM jobs."""
import argparse
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path

def analyze(root):
    def read(name):return json.loads((root/name).read_text())
    four=read('four.json');summary=read('SUMMARY.json');protocol=read('PROTOCOL.json')
    cases=[]
    for name,value in four['cases'].items():
        if name.startswith('patch::long::'):
            _,_,carrier,g,f,d,damage,mode=name.split('::')
            cases.append(dict(name=name,carrier=carrier,generation=int(g[1:]),fuel=int(f[1:]),
                              delay=int(d[1:]),damage=damage,mode=mode,**value))
    if len(cases)!=1350:raise ValueError('Resource grid incomplete')
    def aggregate(rows):
        conditional=[r['p_task_given_full_reserve'] for r in rows if r['p_task_given_full_reserve'] is not None]
        reserve=sum(r['p_full_fixed_reserve'] for r in rows)
        joint=sum(r['p_full_fixed_reserve']*(r['p_task_given_full_reserve'] or 0) for r in rows)
        task=sum(r['p_task_success'] for r in rows)
        return dict(n=len(rows),task_mean=task/len(rows),
                    reserve_mean=reserve/len(rows),defined_conditional_cases=len(conditional),
                    conditional_zero_filled_mean_NOT_probability=sum(conditional)/len(rows),
                    success_without_full_reserve_mass=(task-joint)/len(rows),
                    mean_conditional_over_defined=sum(conditional)/len(conditional) if conditional else None,
                    pooled_conditional_equal_configuration_weight=joint/reserve if reserve else None)
    tables={}
    for axis in ['mode','delay','generation','fuel','damage']:
        group=defaultdict(list)
        for r in cases:
            if axis=='mode' or r['mode']=='on':group[r[axis]].append(r)
        tables[axis]={str(k):aggregate(rs) for k,rs in sorted(group.items())}
    n=summary['paired_primary_states']
    stages={arm:{key:round(value*n) for key,value in summary['panels']['primary:'+arm]['means'].items()}
            for arm in ['A0','A1','A2','A3','A4']}
    exact_delta=Fraction(stages['A1']['Y_star']-stages['A2']['Y_star'],n)
    prediction=protocol['predictions']['predicted_primary_repair_delta']
    contrasts=summary['contrasts']
    if len(contrasts)!=n:raise ValueError('Missing saved contrasts')
    if abs(sum(c['repair'] for c in contrasts)/n-float(exact_delta))>1e-12:raise ValueError('Contrast mismatch')
    success=summary['successful_primary_states']
    condition_matches=all(c['fuel']>=10 and c['material']>=5 and c['ready']==8 for c in success)
    row=read('row1318.json')
    return dict(scope='Saved aggregate recomputation and one raw resource row; no full trajectory replay',
        resource=tables,u008=dict(primary_denominator=n,stages=stages,repair_delta=str(exact_delta),
        versus_intact=str(Fraction(stages['A1']['Y_star']-stages['A0']['Y_star'],n)),
        prediction_matches=abs(prediction-float(exact_delta))<1e-12,
        saved_success_conditions_match=condition_matches,
        bypass_A2=summary['panels']['bypass:A2'],bypass_A3=summary['panels']['bypass:A3'],
        tasks=summary['tasks']),raw_example=dict(case_id=row['case_id'],outcomes=len(row['outcomes'])),
        wave_660_recomputed=False,new_simulations=0,new_vm_jobs=0,
        local_input_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                           for name in ['four.json','SUMMARY.json','PROTOCOL.json','row1318.json']})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=analyze(a.inputs);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
