"""Existing-data parity, exact generator symmetries and a 3x3 Fano positive control."""
import gzip,hashlib,json,sys,time
from pathlib import Path
import numpy as np
from scipy import sparse as sp
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from e002d_exp.model import build
OUT=Path(__file__).parent
def sparsemax(a):return float(np.max(abs(a.data),initial=0))
def main(cache):
 start=time.monotonic();cache=Path(cache);root=cache/'files';run=json.loads((cache/'run.json').read_text())
 for path in ('metrics.json','analysis.json.gz','case_registry.json'):
  b=(root/path).read_bytes();expected=run['files']['files/'+path];assert len(b)==expected['bytes'] and hashlib.sha256(b).hexdigest()==expected['sha256']
 for name in ('e002_exp/model.py','e002c_exp/model.py','e002d_exp/model.py','e002d_exp/plan.py'):
  assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==run['input_sha256'][name]
 metrics=json.loads((root/'metrics.json').read_text());analysis=json.loads(gzip.decompress((root/'analysis.json.gz').read_bytes()))
 rows=[s for s in metrics['cases'] if s['case']['dt']==.005 and s['case']['target']=='base'];parity=[]
 for s in rows:
  c=s['case'];eps=c['detuning']
  if eps<=0:continue
  other=next((x for x in rows if all(x['case'][k]==c[k] for k in ('model','phi_over_pi','dephasing')) and x['case']['detuning']==-eps),None)
  if other is None:continue
  vals=[]
  for x in (other,s):
   ref=x['reference'];vals.append(dict(id=x['case']['id'],epsilon=x['case']['detuning'],h=ref['h'],p=ref['p_m6_N2'],h_m6N2=ref['h_m6_N2'],j=ref['h_m6_N2']/ref['p_m6_N2']))
  parity.append(dict(model=c['model'],phi_over_pi=c['phi_over_pi'],noise=c['dephasing'],epsilon=eps,minus=vals[0],plus=vals[1],h_difference=vals[1]['h']-vals[0]['h'],j_difference=vals[1]['j']-vals[0]['j'],primary_dt_pair=eps==.125))
 curvature=[]
 for noise in (.05,.25):
  for delta in (.0625,.125,.25):
   rr=[next(x for x in analysis['B'] if x['model']==model and x['phi_over_pi']==.5 and x['dephasing']==noise and x['delta']==delta) for model in ('QS','RR_QS')]
   curvature.append(dict(noise=noise,delta=delta,QS=-2*rr[0]['D']['value']/delta**2,RR=-2*rr[1]['D']['value']/delta**2,ratio=rr[0]['D']['value']/rr[1]['D']['value'],statuses=[r['status'] for r in rr]))
 edges=np.array(list(np.ndindex(3,3,3)));perm=[];w=[]
 for n in range(8):
  bits=[(n>>2)&1,(n>>1)&1,n&1];nn=(1-bits[2])*4+(1-bits[1])*2+(1-bits[0])
  for a,b,c in edges:
   perm.append(nn*27+int(b*9+a*3+c));w.append((-1.)**(bits[1]+int(a==2)+int(b==2)+int(c==2)))
 perm=np.array(perm);w=np.array(w);pv=(perm[:,None]+216*perm[None,:]).reshape(-1,order='F');wv=(w[:,None]*w[None,:]).reshape(-1,order='F');W=sp.diags(w);S=sp.diags(wv)
 sym=[]
 for model in ('QS','RR_QS'):
  for phi in (0.,.5):
   cs=[next(x['case'] for x in rows if x['case']['model']==model and x['case']['phi_over_pi']==phi and x['case']['dephasing']==.05 and x['case']['detuning']==e) for e in (-.125,.125)]
   minus,plus=[build(c) for c in cs]
   du=plus['L'][pv,:][:,pv]-minus['L'];da=S@plus['L'].conjugate()@S-minus['L']
   h=plus['currents'][1]+plus['currents'][2];hm=minus['currents'][1]+minus['currents'][2]
   record=dict(model=model,phi_over_pi=phi,unitary_generator_error=sparsemax(du),antiunitary_generator_error=sparsemax(da),unitary_current_error=sparsemax(h[perm,:][:,perm]-(minus['currents'][0]+minus['currents'][2])),antiunitary_current_error=sparsemax(W@h.conjugate()@W-hm))
   assert record['unitary_generator_error']<1e-9 and record['unitary_current_error']<1e-12
   if phi==.5:assert record['antiunitary_generator_error']<1e-12 and record['antiunitary_current_error']<1e-12
   else:assert record['antiunitary_generator_error']>1
   sym.append(record)
 # Frozen m6: source0--sink2 with a side state1. Extra two-port scattering diagnostic.
 # These port self-energies and an energy-resolved incident wave are NOT the E002d pump.
 J=1.;gin=gout=.5;A=J*J+gin*gout/4;tbg=-J*np.sqrt(gin*gout)/A;Tbg=tbg*tbg
 controls=[]
 for v in (.25,.5,1.):
  width=gin*v*v/(2*A);maxerr=0.;zero=None
  for eps in (-1.,-.5,-.125,-.0625,0.,.0625,.125,.5,1.):
   H=np.array([[0.,0.,J],[0.,eps,v],[J,v,0.]],complex);M=-H+.5j*np.diag([gin,0.,gout]);G=np.linalg.inv(M);t=np.sqrt(gin*gout)*G[2,0]
   prediction=tbg*eps/(eps-1j*width);maxerr=max(maxerr,abs(t-prediction));res=tbg*1j*width/(eps-1j*width)
   assert abs(abs(t)**2-(abs(tbg)**2+abs(res)**2+2*(tbg*res.conjugate()).real))<1e-12
   if eps==0:zero=dict(transmission=abs(t)**2,direct_power=Tbg,resonant_power=abs(res)**2,interference=2*(tbg*res.conjugate()).real)
  assert maxerr<1e-12 and zero['transmission']<1e-24
  controls.append(dict(side_coupling=v,width=width,width_over_v_squared=width/v**2,amplitude_identity_error=maxerr,at_resonance=zero))
 # Removing the side branch leaves the ordinary two-port background, including epsilon=0.
 H2=np.array([[0.,J],[J,0.]],complex);G2=np.linalg.inv(-H2+.5j*np.diag([gin,gout]));removed=gin*gout*abs(G2[1,0])**2;assert abs(removed-Tbg)<1e-12
 elapsed=time.monotonic()-start
 out=dict(status='PASS',report_commit='071e15ebc37227b1549e660121bc735a1d86cb13',parity=parity,curvature=curvature,symmetries=sym,
  auxiliary_Fano=dict(scope='Frozen single-excitation m6 with extra coherent two-port scattering boundary; not full E002d NESS current',background_transmission=Tbg,branch_removed_transmission=removed,controls=controls,formula='t=tbg*epsilon/(epsilon-i*width); T=Tbg*epsilon^2/(epsilon^2+width^2); q=0',probe_energy=0.,port_rates=[gin,gout]),
  runtime=dict(expected_seconds=30,lower_seconds=0,upper_seconds=180,actual_seconds=elapsed,status='PASS' if elapsed<=180 else 'INVESTIGATE'),new_evolution_steps=0)
 (OUT/'checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(dict(runtime=out['runtime'],pairs=len(parity),max_total_h_parity_error=max(abs(x['h_difference']) for x in parity),symmetries=sym,curvature=curvature,auxiliary_Fano=out['auxiliary_Fano']),ensure_ascii=False,indent=2))
if __name__=='__main__':main(sys.argv[1])
