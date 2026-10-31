"""Offline scientific audit from hash-verified E002d windows; no new evolution."""
import gzip,io,json,lzma,sys,time,hashlib
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
OUT=Path(__file__).parent
TARGETS={'S2a':(2,5,6),'S2b':(4,3,6),'S1a':(2,1,2),'S1b':(4,1,4),'M2a':(6,5,6),'M2b':(6,3,6),'M1a':(6,1,2),'M1b':(6,1,4)}
def main(cache):
 start=time.monotonic();root=Path(cache)/'files';m=json.loads((root/'metrics.json').read_text());a=json.loads(gzip.decompress((root/'analysis.json.gz').read_bytes()));schema=json.loads((root/'schema.json').read_text())
 cases=m['cases'];zs={};means={};norms={}
 for s in cases:
  c=s['case'];z=np.load(io.BytesIO(lzma.decompress((root/'cases'/(c['id']+'.npz.xz')).read_bytes())),allow_pickle=False)
  zs[c['id']]={k:z[k] for k in ('window_blocks','window_time','window_diagnostics','window_scalar')}
  means[c['id']]=simpson(z['window_blocks'],x=z['window_time'],axis=0)/10
  norms[c['id']]=dict(zip(schema['diagnostics'],simpson(z['window_diagnostics'],x=z['window_time'],axis=0)/10))
 def get(model,target,kind,g=.1,phi=0.,eps=0.,noise=.05):
  return next(s for s in cases if all(s['case'][k]==v for k,v in dict(model=model,target=target,kind=kind,gamma=g,phi_over_pi=phi,detuning=eps,dephasing=noise,dt=.005).items()))
 def base(model):return get(model,'base','base',0.)
 A=[]
 for row in a['A']:
  if row['gamma']!=.1:continue
  rec={k:row[k] for k in ('target','gamma','G0','E','S','eligible','status')};rec['models']={}
  for model in ('QS','RR_QS'):
   ss={k:s for k,s in [('base',base(model)),('T',get(model,row['target'],'T')),('C',get(model,row['target'],'C'))]};cohs={}
   for key in row['coherences'][model]:
    mask,aa,bb=TARGETS[key];n=aa.bit_count();v={k:complex(means[s['case']['id']][mask+1,aa,bb]) for k,s in ss.items()}
    p={k:s['reference'][f'p_m{mask}_N{n}'] for k,s in ss.items()}
    fn={k:norms[s['case']['id']]['full_target_norm_'+key] for k,s in ss.items()}
    records={k:dict(re=c.real,im=c.imag,absolute=abs(c),phase_rad=float(np.angle(c)),sector_weight=p[k],conditional_abs=abs(c)/p[k],full_target_fro=fn[k]) for k,c in v.items()}
    cohs[key]=dict(values=records,suppression_T_vs_base_percent=100*(1-abs(v['T'])/abs(v['base'])),suppression_T_vs_C_percent=100*(1-abs(v['T'])/abs(v['C'])),
      conditional_suppression_T_vs_C_percent=100*(1-(abs(v['T'])/p['T'])/(abs(v['C'])/p['C'])),
      full_norm_suppression_T_vs_base_percent=100*(1-fn['T']/fn['base']),full_norm_suppression_T_vs_C_percent=100*(1-fn['T']/fn['C']),phase_change_rad=float(np.angle(v['T']*v['C'].conjugate())))
   w=sum(x['models'][model]['weight_term'] or 0 for x in row['components']);j=sum(x['models'][model]['conditional_term'] or 0 for x in row['components'])
   collateral=[]
   for mask in sorted({TARGETS[k][0] for k in cohs}):
    for n in (1,2):
     ns=[i for i in range(8) if i.bit_count()==n]
     for ai,aa in enumerate(ns):
      for bb in ns[ai+1:]:
       z={k:means[s['case']['id']][mask+1,aa,bb] for k,s in ss.items()}
       collateral.append(dict(mask=mask,N=n,pair=[aa,bb],complex_values={k:[c.real,c.imag] for k,c in z.items()},T_minus_C_abs=float(abs(z['T']-z['C']))))
   rec['models'][model]=dict(coherences=cohs,collateral=collateral,structure=row['structure'][model],currents=row['models'][model],
     weight_term=w,conditional_term=j,decomposition_error=w+j-row['models'][model]['delta']['value'])
  comp=[dict(mask=x['mask'],N=x['N'],E=x['E']['value'],uncertainty=x['E']['uncertainty'],parts=x['models']) for x in row['components']]
  rec['components']=sorted(comp,key=lambda x:abs(x['E']),reverse=True)
  rec['positive_component_sum']=sum(x['E'] for x in comp if x['E']>0);rec['negative_component_sum']=sum(x['E'] for x in comp if x['E']<0)
  assert abs(sum(x['E'] for x in comp)-row['E']['value'])<1e-12
  A.append(rec)
 additivity=[]
 for k in ('S1','S2'):
  rows=[next(r for r in A if r['target']==t) for t in (k,k+'a',k+'b')];e=rows[0]['E']['value']-rows[1]['E']['value']-rows[2]['E']['value'];u=sum(r['E']['uncertainty'] for r in rows)
  additivity.append(dict(target=k,residual=e,engineering_bound=u,residual_over_bound=abs(e)/u,relative_to_composite_percent=100*e/abs(rows[0]['E']['value']),resolved=abs(e)>u))
 B=[]
 for row in a['B']:
  if row['delta']!=.125:continue
  p=np.array([x['value'] for x in row['p']]);j=np.array([x['value'] for x in row['j']]);h=np.array([x['value'] for x in row['h']])
  w=sum((p[1]-p[i])*(j[1]+j[i])/4 for i in (0,2));c=sum((j[1]-j[i])*(p[1]+p[i])/4 for i in (0,2))
  assert abs(w+c-row['raw_D']['value'])<1e-12
  B.append(dict(model=row['model'],phi_over_pi=row['phi_over_pi'],dephasing=row['dephasing'],D=row['D'],status=row['status'],minimum=row['minimum'],
    j=j.tolist(),h=h.tolist(),p=p.tolist(),D_relative_to_center_percent=100*row['D']['value']/j[1],
    raw_D=row['raw_D'],weight_D=row['weight_D'],raw_D_weight_term=w,raw_D_conditional_term=c,raw_D_weight_fraction=w/row['raw_D']['value'],
    raw_D_conditional_fraction=c/row['raw_D']['value'],D_over_uncertainty=abs(row['D']['value'])/row['D']['uncertainty']))
 C=[]
 for row in a['C']:
  rec={k:row[k] for k in row if k not in ('T','C','baseline')}
  if 'model' in row:
   rec['baseline_D']=row['baseline']['D'];rec['T_D']=row['T']['D'];rec['C_D']=row['C']['D'];rec['T_minus_base_D']=row['T']['D']['value']-row['baseline']['D']['value'];rec['C_minus_base_D']=row['C']['D']['value']-row['baseline']['D']['value']
   rec['T_minus_C_j']=[t['value']-c['value'] for t,c in zip(row['T']['j'],row['C']['j'])]
   rec['effect_relative_to_baseline_D_percent']=100*row['delta_D']['value']/abs(row['baseline']['D']['value'])
   rec['T_j']=row['T']['j'];rec['C_j']=row['C']['j'];rec['T_p']=row['T']['p'];rec['C_p']=row['C']['p']
  rec['effect_over_uncertainty']=abs(row['delta_D']['value'])/row['delta_D']['uncertainty'];C.append(rec)
 # Exact finite-dose identity is not a linearization: physical two-state counterexample.
 bridge=[]
 for g in (.1,1.,2.):
  L0=np.array([[-1.,1.],[1.,-1.]]);V=np.array([[-1.,0.],[1.,0.]]);L=L0+g*V;r0=np.array([.5,.5]);r=np.array([1.,1.+g])/(2.+g);exact=r-r0;derivative=np.linalg.lstsq(np.vstack([L0,np.ones(2)]),np.r_[-V@r0,0.],rcond=None)[0]
  bridge.append(dict(gamma=g,exact_change=exact[1],true_linear_prediction=g*derivative[1],exact_bridge_residual=float(np.linalg.norm(L@exact+g*V@r0))))
 hq=base('QS')['reference']['h'];hr=base('RR_QS')['reference']['h']
 elapsed=time.monotonic()-start
 out=dict(baseline=dict(QS=hq,RR=hr,gap=hq-hr,QS_excess_over_RR_percent=100*(hq/hr-1),RR_deficit_relative_QS_percent=100*(1-hr/hq)),
  A=A,additivity=additivity,B=B,C=C,linear_bridge_counterexample=bridge,
  reported_gate_summary=dict(cases=len(cases),stationary=sum(s['stationarity']['pass_gate'] for s in cases),refinement_statuses={v:sum(s['refinement_status']==v for s in cases) for v in sorted({s['refinement_status'] for s in cases})},max_stationarity_rhs=max(s['stationarity']['rhs'] for s in cases),max_window_drift=max(s['stationarity']['drift'] for s in cases)),
  runtime=dict(actual_seconds=elapsed,expected_seconds=60,lower_seconds=0,upper_seconds=600,status='PASS' if elapsed<=600 else 'INVESTIGATE'))
 serialized=(json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode()
 (OUT/'analysis.json').write_bytes(serialized)
 (OUT/'analysis.json.gz').write_bytes(gzip.compress(serialized,mtime=0))
 print(json.dumps(dict(baseline=out['baseline'],additivity=additivity,B=B,C=[{k:v for k,v in r.items() if k not in ('T_j','C_j','T_p','C_p')} for r in C],gate_summary=out['reported_gate_summary'],runtime=out['runtime']),ensure_ascii=False,indent=2))
if __name__=='__main__':main(sys.argv[1])
