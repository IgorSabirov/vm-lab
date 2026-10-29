"""Synthetic worst-composition serialization test; no physical results are asserted."""
import copy
import json
import tempfile
from pathlib import Path
import numpy as np
from e002c_exp.model import build
from e002c_exp.diagnostics import certificate
from e002c_exp.analysis import summarize
from e002c_exp.ic_status import decide_ic_status
from e002c_exp.export import export_case,manifest,schema,compact_result
from e002_exp.model import save_json

def check():
    model=build(dict(model='QS',phi_over_pi=0.,detuning=0.,dephasing=.05))
    from e002c_exp.diagnostics import expanded
    dn,_,_=expanded(np.eye(216)/216,model)
    dn+=['trace','hermiticity','min_eigen','rhs'];names=model['names']
    rng=np.random.default_rng(20261029)
    series=rng.random((2001,1+len(names)));series[:,0]=np.arange(2001)*.2
    diag=rng.random((201,1+len(dn)));diag[:,0]=np.arange(201)*2
    blocks=np.repeat((np.eye(8)/64)[None],9,axis=0).astype(complex);blocks[0]=np.eye(8)/8
    c=certificate(blocks);certs={k:np.repeat(v[None],201,axis=0) for k,v in c.items()}
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);report=root/'report';report.mkdir();full=root/'full';full.mkdir()
        metrics=dict(identity=dict(run_id='SYNTHETIC_MAXIMUM',source_commit='0'*40),mode='synthetic_only',
                     ic_status='synthetic_not_science',cases=[],work=dict(trajectories=98,steps=4920000))
        checks=dict(runtime_gate=dict(status='NOT_EVALUABLE',expected_seconds=None,lower_seconds=None,upper_seconds=None,actual_seconds=None),summary='SYNTHETIC',failures=[])
        plan=json.loads(Path('experiments/e002c/plan.json').read_text())
        validation=[dict(id=f'IC_VALIDATE_{dt}',model='IC1_QS',dt=dt,phi_over_pi=0.,detuning=0.,dephasing=.05,family='validation',horizon=200.) for dt in (.01,.005)]
        cases=validation+plan['cases']+plan['conditional_ic_cases']
        xs={};results=[];pairs={}
        for case in cases:
            cid=case['id']
            summary=dict(case=case,horizon=400.,requested_horizon=200.,extended=True,failed=None,
                stationarity=dict(pass_gate=False,reason=None,rhs=.12345678901234567,drift=.12345678901234567,flux_range=.12345678901234567),
                transition_reference=dict(zip(names,series[-1,1:].tolist())),refinement_status='not_refined',reference=dict(zip(names,series[-1,1:].tolist())),h_extrema=[.01,.2,.2,2.,2000],
                tau90=123.4,state_status='finite_time_only',dark_geometry=[x['info'] for x in model['dark']],
                node_edge=[dict(time=t,negativity=.12345678901234567,min_eigen=-.12345678901234567,
                status='NODE_EDGE_NPT_DETECTED',independent_reconstruction_from_node_export=False) for t in (0,.2,1,2,5,10,20,50,100,190,200,300,390,400)])
            r=dict(summary=summary,series=series,diagnostics=diag,certs=certs,names=names,dnames=dn)
            xs[cid]=export_case(report,r);results.append(r)
        for r in results:
            c=r['summary']['case']
            fine=next((x for x in results if c['dt']==.01 and x['summary']['case']['dt']==.005 and all(x['summary']['case'][k]==c[k] for k in ('model','phi_over_pi','detuning','dephasing')) and (c['family']=='validation')==(x['summary']['case']['family']=='validation')),None)
            if fine:
                pairs[c['id']]=dict(pass_gate=True,errors={'series':dict.fromkeys(['time']+names,0.),'diagnostics':dict.fromkeys(['time']+dn,0.)})
                r['summary']['refinement_status']=fine['summary']['refinement_status']='passed'
        metrics.update(summarize(results,pairs,'synthetic_only'));metrics.update(**decide_ic_status(None,None),fit=None,ic_validation=None,ic_transport=None)
        checks['pairs']=pairs
        save_json(report/'schema.json',schema(names,dn));save_json(report/'extrema.json',xs)
        save_json(report/'metrics.json',metrics);save_json(report/'checks.json',checks)
        text=compact_result(metrics,checks);(report/'RESULT.md').write_text(text)
        (report/'README.md').write_text('Synthetic exporter test only.\n')
        # Reserve additional real-world metadata: fit log, joints, comparisons, full-file hashes.
        (report/'metadata_reserve.bin').write_bytes(bytes(1024**2))
        budget=manifest(report,full)
        return dict(**budget,result_md_bytes=len(text.encode()),series_columns=len(names)+1,
                    diagnostic_columns=len(dn)+1,evidence_max_bytes=max(p.stat().st_size for p in (report/'evidence').iterdir()),
                    synthetic=True,extra_metadata_reserve=1024**2)

if __name__=='__main__':print(json.dumps(check(),indent=2))
