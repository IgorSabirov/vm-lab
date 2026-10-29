"""Small self-consistent report fixture. No trajectory integration or engine imports."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from e002c_exp.model import ONE,sector_hamiltonian,dark_projectors
from e002c_exp.diagnostics import certificate,negativity,pair_reduction,coherence_values
from e002c_exp.analysis import summarize
from e002c_exp.ic_status import decide_ic_status
from e002c_exp.export import export_case,schema,manifest,compact_result

NAMES=['I01','I12','I02','h','F','n0','n1','n2','pL01','pL12','pL02','ell01','ell12','ell02','pump','break','inventory','source','feed01','feed12','feed02']+[f'{tag}_m{m}' for m in range(8) for tag in ('p','w1','k','d')]

def dump(path,obj):Path(path).write_text(json.dumps(obj,allow_nan=False,indent=2)+'\n')

def make_case(cid,model='QS',dt=.01,horizon=200.,stationary=True,phi=0.,gamma=.05,epsilon=0.,family='synthetic',p7=.1,p6=.2):
    weights=np.array([(1-p7-p6)/6]*6+[p6,p7])
    # Physical two-dimensional PSD block with nonzero imaginary coherence.
    rn=np.zeros((8,8),complex);rn[2,2]=rn[4,4]=.5;rn[2,4]=.4+.2j;rn[4,2]=.4-.2j
    blocks=np.concatenate([rn[None],weights[:,None,None]*rn[None]])
    cert=certificate(blocks);values=dict.fromkeys(NAMES,0.);diag={}
    for m in range(8):
        k,d,iso,inter,_=dark_projectors(sector_hamiltonian(m,phi*np.pi,epsilon))
        sector=blocks[m+1][np.ix_(ONE,ONE)]
        values[f'p_m{m}']=float(np.trace(blocks[m+1]).real);values[f'w1_m{m}']=weights[m]
        values[f'k_m{m}']=float(np.trace(k@sector).real);values[f'd_m{m}']=float(np.trace(d@sector).real)
        diag[f'd_isolated_m{m}']=float(np.trace(iso@sector).real);diag[f'd_interference_m{m}']=float(np.trace(inter@sector).real)
        for edge in ('01','12','02'):diag[f'I{edge}_m{m}']=0.
    for e,edge in enumerate(('01','12','02')):values['pL'+edge]=sum(weights[m] for m in range(8) if m&(1<<e))
    for excluded in range(3):diag[f'pair_N_exclude{excluded}']=negativity(pair_reduction(rn,excluded),[2,2],[0])[0]
    for s in range(9):
        valid=cert['valid'][s];r=blocks[s]/np.trace(blocks[s]).real if valid else None
        for cut in range(3):diag[f'N_s{s}_cut{cut}']=negativity(r,[2,2,2],[cut])[0] if valid else np.nan
        diag[f'W_s{s}']=float(min(cert['alpha'][s]-cert['overlap'][s])) if valid else np.nan;diag[f'valid_s{s}']=float(valid)
    cn,cv=coherence_values(blocks);diag.update(zip(cn,cv));diag.update(trace=0.,hermiticity=0.,min_eigen=0.,rhs=0.)
    dn=[f'I{e}_m{m}' for m in range(8) for e in ('01','12','02')]+[f'd_{tag}_m{m}' for tag in ('isolated','interference') for m in range(8)]+[f'pair_N_exclude{k}' for k in range(3)]
    dn += [k for s in range(9) for k in [*[f'N_s{s}_cut{cut}' for cut in range(3)],f'W_s{s}',f'valid_s{s}']]+cn+['trace','hermiticity','min_eigen','rhs']
    st=np.arange(round(horizon/.2)+1)*.2;dtimes=np.arange(int(horizon//2)+1)*2.
    series=np.column_stack([st,np.tile([values[k] for k in NAMES],(len(st),1))]);diagnostics=np.column_stack([dtimes,np.tile([diag[k] for k in dn],(len(dtimes),1))])
    case=dict(id=cid,model=model,dt=dt,horizon=200.,phi_over_pi=phi,dephasing=gamma,detuning=epsilon,family=family)
    summary=dict(case=case,horizon=horizon,requested_horizon=200.,extended=horizon>200,reference=values.copy(),transition_reference=values.copy() if horizon>=200 else None,
        steps=round(horizon/dt),rhs_calls=4*round(horizon/dt),scalar_records=len(st),diagnostic_records=len(dtimes),snapshots=0,
        stationarity=dict(pass_gate=stationary),refinement_status='not_refined',failed=None,state_status='stationary' if stationary else 'finite_time_only',tau90=0. if stationary else None)
    return dict(summary=summary,series=series,diagnostics=diagnostics,names=NAMES,dnames=dn,certs={k:np.repeat(v[None],len(dtimes),axis=0) for k,v in cert.items()})

def fixture(root,results=None,rejected=False):
    root=Path(root);report=root/'report';report.mkdir();full=root/'full';full.mkdir()
    if results is None:results=[make_case('QS_coarse',p7=1e-6,p6=1e-5)]
    pairs={}
    for r in results:
        c=r['summary']['case']
        if c['dt']!=.01:continue
        fine=next((x for x in results if x['summary']['case']['model']==c['model'] and x['summary']['case']['phi_over_pi']==c['phi_over_pi'] and x['summary']['case']['dephasing']==c['dephasing'] and x['summary']['case']['detuning']==c['detuning'] and x['summary']['case']['dt']==.005),None)
        if fine:
            pairs[c['id']]=dict(pass_gate=True,errors={key:{name:0. for name in ['time']+(r['names'] if key=='series' else r['dnames'])} for key in ('series','diagnostics')})
            r['summary']['refinement_status']=fine['summary']['refinement_status']='passed'
    xs={}
    for r in results:
        cid=r['summary']['case']['id'];xs[cid]=export_case(report,r);r['summary']['h_extrema']=xs[cid]['h_t_positive']
    metrics=summarize(results,pairs,'synthetic_fixture');fit=None;validation=None
    if rejected:
        raw=json.dumps({'alpha':[.1,.1,.1]},sort_keys=True).encode();(report/'selected_alpha.json').write_bytes(raw)
        fit=dict(selected={'alpha':[.1,.1,.1]},selected_alpha_sha256=hashlib.sha256(raw).hexdigest());validation=dict(structural_pass=False)
    metrics.update(identity=dict(run_id='SYNTHETIC_FIXTURE',source_commit='0'*40),mode='synthetic_fixture',fit=fit,ic_validation=validation,ic_transport=None,
                   **decide_ic_status(fit,validation),work=dict(trajectories=len(results)))
    checks=dict(export_complete=True,pairs=pairs,failures=[],summary='SYNTHETIC_ONLY',runtime_gate=dict(status='NOT_EVALUABLE',expected_seconds=None,lower_seconds=None,upper_seconds=None,actual_seconds=None))
    dump(report/'metrics.json',metrics);dump(report/'checks.json',checks);dump(report/'extrema.json',xs);dump(report/'schema.json',schema(results[0]['names'],results[0]['dnames']))
    with (report/'cases.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,['id']);writer.writeheader();writer.writerows({'id':r['summary']['case']['id']} for r in results)
    (report/'RESULT.md').write_text(compact_result(metrics,checks));(report/'README.md').write_text('Synthetic fixture, not a Lindblad trajectory.\n')
    manifest(report,full);return report

def repack(report):manifest(report,report.parent/'full')
