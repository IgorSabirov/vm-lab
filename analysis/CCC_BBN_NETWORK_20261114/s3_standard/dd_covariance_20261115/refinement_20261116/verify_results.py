"""Offline verification and compact scientific tables for the eight raw outputs."""
from pathlib import Path
import hashlib,json,math

HERE=Path(__file__).resolve().parent
OUT=HERE/'results/S3_DD_CONVERGENCE_20261116_r1'
def read(p):return json.loads(p.read_text())
def close(x,y):assert math.isclose(x,y,rel_tol=2e-12,abs_tol=2e-15),(x,y)
def main():
    s=read(OUT/'SUMMARY.json');m=read(OUT/'ARTIFACTS.json');checks=0
    for e in m['files']:
        p=OUT/e['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256'];assert p.stat().st_size==e['bytes'];checks+=1
    runs={p.parent.name:read(p) for p in OUT.glob('*/RESULT.json')};assert len(runs)==8
    for r in runs.values():
        n,H,d,t,he3,he4,li,be=r['final'];v={'D_H':d/H,'Yp':4*he4,'He3_H_late':(he3+t)/H,'Li7_H_late':(li+be)/H}
        for k,x in v.items():close(x,r['observables'][k])
        assert r['source_sha']==s['source_sha'] and r['q_other_reactions']==0
        assert r['post_decay_projection_applied'] and r['observation_epoch']=='complete_decay_limit'
        assert r['supervisor']['process_exited'] and r['supervisor']['exit_code']==0
        assert r['background_sha256']=='e1289712d2c6701ad89269984721e468415a261b559f7f972893cf72324e11f3'
    rows=[];contributions={}
    for obs,v in s['results'].items():
        for ch in ['ddHe3n','ddtp']:
            for h in [.25,.125]:
                tag=str(h).replace('.','_');a=(math.log(runs[f'{ch}_plus_{tag}']['observables'][obs])-math.log(runs[f'{ch}_minus_{tag}']['observables'][obs]))/(2*h)
                close(a,v['derivatives'][ch][str(h)])
            x,y=[v['derivatives'][ch][str(h)] for h in [.25,.125]]
            gap=abs(x-y)/max(abs(x),abs(y));close(gap,v['step_diagnostics'][ch]['0.25_to_0.125']['relative_discrepancy'])
            rows.append({'observable':obs,'channel':ch,'a_h0_25':x,'a_h0_125':y,'gap_percent':100*gap,'p':v['order_diagnostics'][ch]['p'],'status':v['step_diagnostics'][ch]['0.25_to_0.125']['status']})
        for h in ['0.25','0.125']:
            a,b=[v['derivatives'][ch][h] for ch in ['ddHe3n','ddtp']];close(2*a*b/(a*a+b*b),v['by_step'][h]['kappa'])
        if obs in ['He3_H_late','Li7_H_late']:
            indices=[4,3] if obs=='He3_H_late' else [6,7];names=['He3','T'] if obs=='He3_H_late' else ['Li7','Be7'];contributions[obs]={}
            for ch in ['ddHe3n','ddtp']:
                a,b=[runs[f'{ch}_{sign}_0_125']['final'] for sign in ['plus','minus']]
                ap=[a[i]/a[1] for i in indices];bp=[b[i]/b[1] for i in indices]
                sp,sm=sum(ap),sum(bp);L=(sp-sm)/(math.log(sp)-math.log(sm))
                values=[(x-y)/(.25*L) for x,y in zip(ap,bp)]
                close(sum(values),v['derivatives'][ch]['0.125']);contributions[obs][ch]=dict(zip(names,values))
    result={'status':'PASS','verified_artifact_hashes':checks,'raw_integrations':len(runs),'new_derivatives_verified':16,
        'arithmetic_tolerance':{'relative':2e-12,'absolute':2e-15,'is_solver_error_estimate':False},
        'rows':rows,'finite_window_component_contributions_h0_125':contributions,
        't_network_start_seconds':next(iter(runs.values()))['t_network_start_seconds'],
        't_network_end_seconds':next(iter(runs.values()))['t_network_end_seconds'],
        'scientific_acceptance':False}
    (HERE/'VERIFICATION.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
