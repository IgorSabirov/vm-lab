"""Analyze only the already verified G/baseline reports; never solve held-out cases."""
import hashlib,json,time
from pathlib import Path
import numpy as np
from infra.github_result_reader import read_github_result
from e002e_exp.plan import selected_work

ROOT=Path(__file__).resolve().parents[2]
DEST=Path(__file__).resolve().parent
SOURCES={
 'G':('E002e_G_v001_r002','91d8bc40b266effd71e7211dda6fe88f5fb7c9b3','9112ff1a5205a40ce1604a42212d3a6d4baa13ae'),
 'baseline':('E002e_BASELINE_v001_r001','517217b5cb1e56dcb0e9cfd35a74e51fb202a49c','464e7d2ec560426ae106c6d607f47a7a6b667cc9')}

def save(name,obj):
    (DEST/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def scalar(x):
    if isinstance(x,dict):return complex(x['re'],x['im'])
    return complex(x)

def contrast(line,delta,key='j6'):
    if not {-delta,0.,delta}<=line.keys():return None
    xs=[line[e]['conditional'].get(key,{}) for e in (0.,-delta,delta)]
    if any(x.get('value') is None for x in xs):return dict(status='UNRESOLVED')
    value=xs[0]['value']-.5*(xs[1]['value']+xs[2]['value'])
    u=xs[0]['uncertainty']+.5*(xs[1]['uncertainty']+xs[2]['uncertainty'])
    return dict(value=value,uncertainty=u,relative_depth=-value/xs[0]['value'] if xs[0]['value'] else None,
                center=xs[0]['value'],center_below_both=xs[0]['value']<min(xs[1]['value'],xs[2]['value']),status='RESOLVED')

def main():
    start=time.perf_counter();reports={};inputs=[]
    for stage,(rid,ref,source) in SOURCES.items():
        reports[stage]=read_github_result(lambda repo,path,ref:(ROOT/path).read_bytes(),repository='IgorSabirov/vm-lab',result_commit=ref,run_id=rid,source_commit=source)
        assert reports[stage]['execution_succeeded']
    def read(stage,name,block):
        rid,ref,_=SOURCES[stage];path=f'results/{rid}/files/{name}'
        b=(ROOT/path).read_bytes();meta=reports[stage]['report']['files']['files/'+name]
        assert len(b)==meta['bytes'] and hashlib.sha256(b).hexdigest()==meta['sha256']
        inputs.append(dict(id=stage+'_'+name,block=block,report_commit=ref,path=path,sha256=meta['sha256'],bytes=meta['bytes']))
        return json.loads(b)
    small=[read('G',f'small_{i:03d}.json','G') for i in range(92)]
    full=[read('baseline',c['id']+'.json','R_baseline' if c['block']=='R' else 'F1_v_equals_J') for c in selected_work('baseline')['full']]
    responses=read('baseline','responses.json','F3_baseline_if_declared')
    metrics=read('baseline','metrics.json','T_baseline_if_declared')
    full_lines=[]
    for model in ('QS','RR_QS','IC1_QS'):
        line={r['case']['epsilon']:r for r in full if r['case']['model']==model and r['case']['phi_over_pi']==.5}
        full_lines.append(dict(model=model,points=[dict(epsilon=e,id=r['id'],j6=r['conditional']['j6'],h6=r['raw']['h6'],p6=r['raw']['P_m6_N2'],F=r['raw']['F']) for e,r in sorted(line.items())],
            contrasts={str(d):contrast(line,d) for d in (.0625,.125,.25,.5) if contrast(line,d) is not None},background='UNRESOLVED',width='UNRESOLVED'))
    groups={}
    for r in small:
        c=r['case'];key=(c['block'],c['dimension'],c['mask'],c['phi_over_pi'],c.get('v_over_J',1.))
        groups.setdefault(key,{})[c['epsilon']]=r
    small_lines=[]
    for key,line in groups.items():
        block,dim,mask,phi,v=key
        small_lines.append(dict(block=block,dimension=dim,mask=mask,phi=phi,v=v,
            points=[dict(epsilon=e,id=r['id'],F=r['raw']['F'],p_e=r['raw']['p_e'],j1=r['conditional']['j_N1']['value'],j2=r['conditional']['j_N2']['value'],p2=r['raw']['p_N2'],renewal=r['renewal']) for e,r in sorted(line.items())],
            contrasts={metric:{str(d):contrast(line,d,metric) for d in (.125,.5) if contrast(line,d,metric) is not None} for metric in ('j_N1','j_N2','F_over_p_e')}))
    static=[]
    for model in ('QS','RR_QS','IC1_QS'):
        recs={r['id']:r for r in full if r['case']['model']==model}
        for target in ('M1','M2','S2a','S2b','S1a','S1b'):
            rs=[r for r in responses if r['kind']=='static' and r['target']==target and r['base_id'] in recs]
            vals={recs[r['base_id']]['case']['epsilon']:r for r in rs}
            if not vals:continue
            points=[dict(epsilon=e,case_id=r['base_id'],j6_derivative=scalar(r['values']['j6']).real,h6_derivative=scalar(r['values']['h6']).real,p6_derivative=scalar(r['values']['P_m6_N2']).real,j6_uncertainty=r['uncertainty']['j6']) for e,r in sorted(vals.items())]
            dc=None
            if {-.125,0.,.125}<=vals.keys():dc=scalar(vals[0.]['values']['j6']).real-.5*(scalar(vals[-.125]['values']['j6']).real+scalar(vals[.125]['values']['j6']).real)
            static.append(dict(model=model,target=target,points=points,D125_derivative=dc))
    frequency=[]
    for model in ('QS','RR_QS'):
        ids={r['id'] for r in full if r['case']['model']==model}
        rs=sorted([r for r in responses if r['kind']=='frequency' and r['base_id'] in ids],key=lambda r:r['omega'])
        frequency.append(dict(model=model,points=[dict(omega=r['omega'],**{k:dict(re=scalar(r['values'][k]).real,im=scalar(r['values'][k]).imag,abs2=abs(scalar(r['values'][k]))**2) for k in ('J_h','j6','K','P_m6_N2')}) for r in rs]))
    qrt=[]
    for row in metrics['qrt']:
        rec=next(r for r in full if r['id']==row['id']);name=row['id']+'_qrt.npz'
        rid,ref,_=SOURCES['baseline'];path=f'results/{rid}/files/{name}';b=(ROOT/path).read_bytes();meta=reports['baseline']['report']['files']['files/'+name]
        assert hashlib.sha256(b).hexdigest()==meta['sha256']
        inputs.append(dict(id='baseline_'+name,block='T_baseline_if_declared',report_commit=ref,path=path,sha256=meta['sha256'],bytes=meta['bytes']))
        with np.load(ROOT/path) as a:
            C=a['C'];t=a['time'];variances=np.real(np.diagonal(C[0]));tau=np.trapezoid(np.abs(np.diagonal(C,axis1=1,axis2=2)),x=t,axis=0)/variances
        assert np.max(abs(tau-np.array(row['fine']['tau_int_truncated'])))<1e-10
        qrt.append(dict(model=rec['case']['model'],phi=rec['case']['phi_over_pi'],id=row['id'],H=float(t[-1]),samples=len(t),tau_abs_H100=tau.tolist(),variances=variances.tolist(),late_window_max=row['fine']['late_window_abs_max'],max_scaled_dt=row['refinement']['max_scaled'],tail_status=row['fine']['tail_status']))
    result=dict(source_reports={k:dict(run_id=v[0],report_commit=v[1],source_commit=v[2]) for k,v in SOURCES.items()},
        full_lines=full_lines,small_lines=small_lines,static=static,frequency=frequency,qrt=qrt,
        scientific_scope='Training analysis only; no full-model F2 outcomes viewed',internal_seconds=time.perf_counter()-start)
    save('training_analysis.json',result);save('training_inputs.json',inputs)
    save('baseline_bundle.json',dict(status='VERIFIED_GITHUB',source_run=SOURCES['baseline'][0],source_report_commit=SOURCES['baseline'][1],records=full))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
