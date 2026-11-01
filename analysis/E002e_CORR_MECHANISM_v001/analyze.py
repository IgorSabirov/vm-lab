"""Published-data accounting only: no Liouvillian assembly or physical solves."""
import time
START=time.perf_counter()
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from e002e_corr_exp.environment import environment
from e002e_corr_exp.verify import verify_report
from e002e_exp.runtime import compare_environment
DEST=Path(__file__).resolve().parent
MODELS={'QS':'full_7c1820e764ee','RR_QS':'full_5222212ebc04','IC1_QS':'full_a2a1b36cf33b'}
CORR=ROOT/'results/E002e_CORR_v001_r001/files'

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def scalar(value):
    return complex(value['re'],value['im']) if isinstance(value,dict) else complex(value)

def load():
    manifest=json.loads((DEST/'INPUTS.json').read_text())
    for spec in manifest['files']:
        raw=(ROOT/spec['path']).read_bytes()
        if (len(raw)!=spec['bytes'] or hashlib.sha256(raw).hexdigest()!=spec['sha256']
            or hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=spec['git_blob']):
            raise ValueError('Input identity mismatch: '+spec['path'])
    verified=verify_report(CORR)
    data={}
    for model,cid in MODELS.items():
        with np.load(CORR/(cid+'_series.npz'),allow_pickle=False) as a:
            data[model]={k:a[k].copy() for k in a.files}
        data[model]['record']=json.loads((CORR/(cid+'_case.json')).read_text())
    return data,dict(files=len(manifest['files']),bytes=sum(s['bytes'] for s in manifest['files']),verification=verified)

def filtered(t,x):
    """Exact solution for linear interpolation of x: y'=k(x-y), y(0)=0."""
    h=np.diff(t)
    if not np.allclose(h,h[0],atol=1e-12,rtol=0):raise ValueError('Nonuniform export grid')
    kh=.5*h[0];a=np.exp(-kh);b=-np.expm1(-kh)/kh
    left=b-a;right=1-b
    y=np.zeros_like(x,dtype=float)
    for i in range(1,len(t)):y[i]=a*y[i-1]+left*x[i-1]+right*x[i]
    return y

def crossings(t,y,threshold=1e-9):
    indices=np.flatnonzero(np.abs(y)>threshold);out=[]
    for i,j in zip(indices[:-1],indices[1:]):
        if y[i]*y[j]<0:
            out.append(dict(left=float(t[i]),right=float(t[j]),linear_estimate=float(t[i]-y[i]*(t[j]-t[i])/(y[j]-y[i])),direction='negative_to_positive' if y[i]<0 else 'positive_to_negative'))
    return out

def summarize(t,y):
    return dict(initial=float(y[0]),final=float(y[-1]),minimum=float(y.min()),maximum=float(y.max()),
        time_minimum=float(t[y.argmin()]),time_maximum=float(t[y.argmax()]),
        signed_area=float(np.trapezoid(y,t)),positive_area=float(np.trapezoid(np.maximum(y,0),t)),
        negative_area=float(np.trapezoid(np.minimum(y,0),t)),crossings=crossings(t,y))

def decompose(a,label):
    t=a[label+'_sample_time'];raw=a[label+'_raw'];names=list(a['names'])
    delta=raw[:,:,1]-raw[:,:,0]
    col=lambda n:delta[:,names.index(n)]
    full=lambda n:raw[:,names.index(n),:]
    terms={}
    for tag,mask in [('S',None),('M',6)]:
        for N in (1,2):
            terms[f'I12_m{2 if mask is None else 6}_N{N}']=-2*col(f'C_{tag}{N}a').imag
            terms[f'I02_m{4 if mask is None else 6}_N{N}']=2*col(f'C_{tag}{N}b').real
    exact_h6=-2*full('C_M2a').imag+2*full('C_M2b').real
    algebra=dict(h6=float(np.max(abs(full('h6')-exact_h6))),
        output_currents=float(np.max(abs(full('J_h')-full('current_1')-full('current_2')))),
        output_population=float(np.max(abs(full('F')-.5*full('node_2')))))
    if max(algebra.values())>1e-11:raise ArithmeticError('Exact operator accounting failed: '+str(algebra))
    terms['I12_remaining_m3_m7']=col('current_1').real-sum(v for k,v in terms.items() if k.startswith('I12_'))
    terms['I02_remaining_m5_m7']=col('current_2').real-sum(v for k,v in terms.items() if k.startswith('I02_'))
    keys=list(terms);x=np.column_stack(list(terms.values()));fparts=filtered(t,x)
    fparts_sparse=filtered(t[::2],x[::2]);reconstruction=fparts.sum(axis=1)
    defect=float(np.max(abs(reconstruction-col('F').real)))
    if defect>5e-5:raise ArithmeticError('Export-grid flux reconstruction exceeds declared cap')
    # Integrate the filter ODE exactly for the chosen linear interpolant.
    areas=np.trapezoid(x,t,axis=0)-2*fparts[-1]
    sparse_areas=np.trapezoid(x[::2],t[::2],axis=0)-2*fparts_sparse[-1]
    tf=a[label+'_time'];df=np.diff(a[label+'_flux'],axis=1)[:,0]
    flux_area=float(np.trapezoid(df,tf));dense_defect=float(abs(areas.sum()-flux_area))
    budget=3*abs(areas-sparse_areas)+dense_defect
    channels={k:dict(current=summarize(t,x[:,i]),filtered_final=float(fparts[-1,i]),
              flux_signed_area=float(areas[i]),sampling_uncertainty_proxy=float(budget[i]),
              flux_at_total_positive_peak=float(np.interp(tf[df.argmax()],t,fparts[:,i]))) for i,k in enumerate(keys)}
    return dict(flux=summarize(tf,df),exact_identities=algebra,channels=channels,
        reconstruction=dict(maximum_pointwise_defect=defect,signed_area_defect=dense_defect,
            sample_grid_halving_maximum=float(np.max(abs(fparts[::2]-fparts_sparse))),method='EXACT_FILTER_OF_PIECEWISE_LINEAR_EXPORTED_CURRENT',
            not_independent_causal_mechanisms=True),
        raw_diagnostics={n:summarize(t,col(n).real) for n in ('J_h','current_0','current_1','current_2','h6','P_m6_N2','source','inventory','mask_6','mask_7')},
        snapshots=[dict(time=float(t[i]),delta_flux=float(col('F')[i].real),delta_I12=float(col('current_1')[i].real),
                    delta_I02=float(col('current_2')[i].real),delta_h6=float(col('h6')[i].real),
                    delta_p6=float(col('P_m6_N2')[i].real),filtered_channels={k:float(fparts[i,j]) for j,k in enumerate(keys)})
                   for i in sorted({0,50,100,250,500,1000,int(np.abs(t-tf[df.argmax()]).argmin())})])

def primitive_summary(values):
    v={k:scalar(x).real for k,x in values.items() if x is not None and not k.startswith('C_')}
    return dict(F=v['F'],J_h=v['J_h'],I12=(v['J_h']+v['K'])/2,I02=(v['J_h']-v['K'])/2,
                h6=v['h6'],p6=v['P_m6_N2'],
                N1=sum(v[f'h_m{m}_N1'] for m in range(8)),N2=sum(v[f'h_m{m}_N2'] for m in range(8)),
                I12_m6_N2=v['I12_m6_N2'],I02_m6_N2=v['I02_m6_N2'])

def comparisons():
    base={model:json.loads((ROOT/'results/E002e_BASELINE_v001_r001/files'/(cid+'.json')).read_text()) for model,cid in MODELS.items()}
    baseline={m:primitive_summary(r['raw']) for m,r in base.items()}
    responses=json.loads((ROOT/'results/E002e_BASELINE_v001_r001/files/responses.json').read_text())
    static=[]
    for m,cid in MODELS.items():
        for r in responses:
            if r['base_id']!=cid or r['kind']!='static':continue
            if r['target'] not in ('M1','M2'):raise ValueError('Unexpected matching static control')
            if not r['refinement_gate']['pass_gate']:raise ValueError('Unverified static response')
            static.append(dict(model=m,target=r['target'],derivatives=primitive_summary(r['values']),
                               meaning='T_MINUS_C_DERIVATIVE_NOT_A_STANDALONE_CPTP_GENERATOR'))
    f2=[]
    for cid in ('full_4d0b6dc1ce16','full_661414372cbf','full_9217f12319ec','full_d269932a5ccc'):
        r=json.loads((ROOT/'results/E002e_F2_v001_r001/files'/(cid+'.json')).read_text());c=r['case']
        assert c['epsilon']==0 and c['phi_over_pi']==.5 and c['node_noise']==.05
        assert r['quality']['pass'] and r['refinement']['gate']['pass_gate']
        vals=primitive_summary(r['raw']);b=baseline[c['model']]
        f2.append(dict(model=c['model'],v=c['m6_v_over_J'],values=vals,change_from_v1={k:vals[k]-b[k] for k in vals},
                       interpretation='STATE_AND_CURRENT_OPERATOR_BOTH_CHANGE'))
    return dict(baselines=baseline,R=static,F2=f2)

def main():
    mode=sys.argv[1];data,inputs=load();env=environment();loaded=time.perf_counter()-START
    if mode=='calibrate':
        out=dict(status='NOT_EVALUABLE_FIRST_ANALYZER_IO_CALIBRATION',expected_seconds=.6,lower_seconds=.25,upper_seconds=1.5,
                 actual_seconds=loaded,environment=env,inputs=inputs,scientific_analysis_performed=False,
                 archive_accessed=False,new_NESS=0,new_physical_steps=0)
        dump(DEST/'io_probe.json',out);print(json.dumps(out));return
    forecast=json.loads((DEST/'FORECAST.json').read_text());reference=json.loads((DEST/'io_probe.json').read_text())
    match=compare_environment(reference['environment'],env)
    if not match['comparable']:raise ValueError('Analyzer environment changed')
    test_t=np.linspace(0,2,101)
    test_x=np.column_stack((np.ones_like(test_t),test_t))
    expected=np.column_stack((1-np.exp(-.5*test_t),test_t-2+2*np.exp(-.5*test_t)))
    filter_analytic_error=float(np.max(abs(filtered(test_t,test_x)-expected)))
    if filter_analytic_error>1e-12:raise ArithmeticError('Independent analytic filter check failed')
    start=time.perf_counter();out={};count=0
    for model,a in data.items():
        rows={label:decompose(a,label) for label in ('fine','coarse','reference')};count+=3
        out[model]=dict(variants=rows,baseline_flux=a['record']['baseline'][0]['F'],primary=a['record']['result']['primary'])
        for k,r in rows['fine']['channels'].items():
            differences=[abs(r['flux_signed_area']-rows[label]['channels'][k]['flux_signed_area']) for label in ('coarse','reference')]
            r['numerical_variant_uncertainty_proxy']=3*sum(differences)
    result=dict(status='RETROSPECTIVE_ACCOUNTING_NOT_NEW_PHYSICS',filter_analytic_error=filter_analytic_error,models=out,comparisons=comparisons(),
                limitations=['Absolute primary does not split additively.','Current convolution is a balance identity, not an independent intervention.','Only selected masks and sectors resolve; remainder is explicit.','No infinite-tail bound or stationary reset susceptibility is inferred.'])
    dump(DEST/'analysis.json',result);elapsed=time.perf_counter()-START
    status='PASS' if match['comparable'] and forecast['lower_seconds']<=elapsed<=forecast['upper_seconds'] else 'REVIEW_REQUIRED'
    runtime=dict(status=status,actual_seconds=elapsed,forecast=forecast,deviation_seconds=elapsed-forecast['expected_seconds'],
        environment=env,environment_comparison=match,inputs=inputs,load_verify_seconds=loaded,analysis_save_seconds=time.perf_counter()-start,
        variants=count,filter_steps=13500,full_physical_steps=0,new_NESS=0,archive_accessed=False,
        timing_scope='Python body through analysis JSON write; final runtime metadata/interpreter start excluded')
    dump(DEST/'runtime.json',runtime);print(json.dumps(runtime))

if __name__=='__main__':main()
