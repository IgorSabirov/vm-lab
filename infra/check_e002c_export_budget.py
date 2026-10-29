"""Synthetic worst-composition serialization test; no physical results are asserted."""
import copy
import json
import tempfile
from pathlib import Path
import numpy as np
from e002c_exp.model import build
from e002c_exp.diagnostics import certificate
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
        xs={}
        for i in range(98):
            cid=f'IC1_QS_P{i+1:02d}_dt005';case=dict(id=cid,model='IC1_QS',dt=.005,phi_over_pi=.5,detuning=-.5,dephasing=.25,family='synthetic')
            summary=dict(case=case,horizon=400.,reference=dict(zip(names,series[-1,1:].tolist())),h_extrema=[.01,.2,.2,2.,2000],
                tau90=123.4,state_status='finite_time_only',dark_geometry=[x['info'] for x in model['dark']],
                node_edge=[dict(time=t,negativity=.12345678901234567,min_eigen=-.12345678901234567,
                status='NODE_EDGE_NPT_DETECTED',independent_reconstruction_from_node_export=False) for t in (0,.2,1,2,5,10,20,50,100,190,200,300,390,400)])
            r=dict(summary=summary,series=series,diagnostics=diag,certs=certs,names=names,dnames=dn)
            xs[cid]=export_case(report,r);metrics['cases'].append(summary)
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
