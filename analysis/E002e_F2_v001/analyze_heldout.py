"""Post-run arithmetic verification; no new numerical solves or fitted parameters."""
from pathlib import Path
from collections import Counter,defaultdict
import json,math
from e002e_exp.plan import selected_work,full_physical_key

ROOT=Path(__file__).resolve().parents[2];D=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def eq(a,b):assert math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-15),(a,b)
def main():
    P=ROOT/'results/E002e_F2_v001_r001/files';pred=read(D/'f2_prereg_predictions.json')
    baseline=read(D/'baseline_bundle.json')['records'];refs={full_physical_key(r['case']):r for r in baseline}
    rows={c['id']:read(P/(c['id']+'.json')) for c in selected_work('F2')['full']}
    published={r['prediction_id']:r for r in read(P/'prediction_verdicts.json')}
    differences={r['id']:r for r in read(P/'f2_differences.json')};audit=[];families=defaultdict(Counter)
    for r in rows.values():
        b=refs[full_physical_key(r['case'],undeformed=True)]
        for x in (r,b):assert x['raw']['P_m6_N2']>max(1e-6,x['primitive_uncertainty']['P_m6_N2'])
        for name in ('J_h','h6','P_m6_N2'):
            eq(differences[r['id']]['changes'][name],r['raw'][name]-b['raw'][name])
        eq(differences[r['id']]['changes']['j6'],r['conditional']['j6']['value']-b['conditional']['j6']['value'])
    for p in pred['predictions']:
        value=0.;error=0.
        for term in p['observable_definition']['linear_terms']:
            r=rows[term['case_id']];b=refs[full_physical_key(r['case'],undeformed=True)]
            v=r['conditional']['j6']['value'];u=r['conditional']['j6']['uncertainty']
            if p['observable_definition']['kind']=='baseline_difference':v-=b['conditional']['j6']['value'];u+=b['conditional']['j6']['uncertainty']
            value+=term['coefficient']*v;error+=abs(term['coefficient'])*u
        lo,hi=value-error,value+error;tol=p['tolerance_and_error_rule']['absolute_tolerance'];expected=p['expected_value_or_sign_or_interval']
        if p['prediction_type']=='sign':
            assert expected==1
            status='SUPPORTED_WITHIN_DECLARED_TOLERANCE' if lo>tol else ('PREDICTION_FAILED' if hi < -tol else 'NUMERICALLY_UNRESOLVED')
        else:
            a,b=expected-tol,expected+tol
            status='SUPPORTED_WITHIN_DECLARED_TOLERANCE' if lo>=a and hi<=b else ('PREDICTION_FAILED' if hi<a or lo>b else 'NUMERICALLY_UNRESOLVED')
        got=published[p['prediction_id']];eq(value,got['value']);eq(error,got['uncertainty']);assert status==got['status']
        audit.append(dict(id=p['prediction_id'],family=p['family'],expected=expected,tolerance=tol,actual=value,numerical_uncertainty=error,status=status));families[p['family']][status]+=1
    lines=[]
    for model in ('QS','RR_QS'):
        for v in (1.,.5,0.):
            rr=[r for r in (baseline if v==1 else rows.values()) if r['case']['model']==model and r['case']['m6_v_over_J']==v and r['case']['phi_over_pi']==.5]
            line={r['case']['epsilon']:r for r in rr};j={e:r['conditional']['j6']['value'] for e,r in line.items()};c=line[0.]
            ds={str(d):j[0.]-.5*(j[-d]+j[d]) for d in (.125,.5)}
            lines.append(dict(model=model,v=v,j0=j[0.],h0=c['raw']['h6'],p0=c['raw']['P_m6_N2'],D=ds,relative_depth={k:-x/j[0.] for k,x in ds.items()},curvature={k:-2*x/float(k)**2 for k,x in ds.items()},points=[dict(epsilon=e,j6=j[e],uncertainty=r['conditional']['j6']['uncertainty'],h6=r['raw']['h6'],p6=r['raw']['P_m6_N2']) for e,r in sorted(line.items())]))
    metrics=read(P/'metrics.json');costs=defaultdict(lambda:dict(cases=0,total_case_seconds=0.,setup_seconds=0.,factor_seconds=0.,iterative_solve_seconds=0.,iterations=[]))
    for row in metrics['phases']:
        model=rows[row['id']]['case']['model'];s=costs[model];s['cases']+=1
        for key in ('total_case_seconds','setup_seconds'):s[key]+=row[key]
        s['factor_seconds']+=row['solver']['factor_seconds']+row['refinement_solver']['factor_seconds'];s['iterative_solve_seconds']+=row['refinement_solver']['solve_seconds'];s['iterations'].append(row['refinement_solver']['iterations'])
    symmetry=read(P/'symmetry_pairs.json')
    out=dict(status='PUBLISHED_VERDICTS_INDEPENDENTLY_REPRODUCED',run_id='E002e_F2_v001_r001',report_commit='6e9e915986293db9d6702e7f54021115a5c28b02',prediction_commit='11fa1009090d58dd30fa0a285ff4ed83c60c6f79',families={k:dict(v) for k,v in families.items()},verdicts=audit,lines=lines,costs=dict(costs),symmetry=dict(count=len(symmetry),statuses=dict(Counter(x['status'] for x in symmetry)),max_absolute_error=max(x['error'] for x in symmetry)),width_status='UNRESOLVED',background_status='UNRESOLVED',scientific_acceptance=False)
    (D/'heldout_analysis.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(out))

if __name__=='__main__':main()
