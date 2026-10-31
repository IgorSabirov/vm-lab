"""Targeted full-state audit; no time integration or steady-state solve."""
import hashlib,json,sys,time,lzma,io
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from e002d_exp.model import build
from e002d_exp.plan import TARGETS

def main(cache,full):
 start=time.monotonic();cache=Path(cache);full=Path(full);outdir=Path(__file__).parent
 run=json.loads((cache/'run.json').read_text());m=json.loads((cache/'files/metrics.json').read_text())
 for path in ('e002_exp/model.py','e002c_exp/model.py','e002d_exp/model.py','e002d_exp/plan.py'):
  assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==run['input_sha256'][path]
 schema=json.loads((cache/'files/schema.json').read_text());manifest=json.loads((outdir/'full_data_manifest.json').read_text())
 sums={s['case']['id']:s for s in m['cases']};models={};states={};checks=[]
 edges=np.array(list(np.ndindex(3,3,3)));masks=((edges==2)*[1,2,4]).sum(axis=1)
 for file in manifest:
  cid=file['id'];raw=(full/(cid+'.npz')).read_bytes();assert len(raw)==file['bytes'] and hashlib.sha256(raw).hexdigest()==file['sha256']
  rho=np.load(io.BytesIO(raw),allow_pickle=False)['rho'];c=sums[cid]['case'];b=build(c);v=rho.reshape(-1,order='F')
  states[cid]=rho;models[cid]=b
  vals=np.asarray(b['rows']@v);eig=np.linalg.eigvalsh(rho)
  reduced=np.zeros((9,8,8),complex)
  for e in range(27):reduced[masks[e]+1]+=rho[e::27,e::27]
  reduced[0]=reduced[1:].sum(axis=0)
  z=np.load(io.BytesIO(lzma.decompress((cache/'files/cases'/(cid+'.npz.xz')).read_bytes())),allow_pickle=False)
  assert z['window_time'][-1]==200
  norms={};error=0.
  for key,(mask,a,bb) in TARGETS.items():
   e=np.flatnonzero(masks==mask);value=float(np.linalg.norm(rho[np.ix_(a*27+e,bb*27+e)]));norms[key]=value
   published=z['window_diagnostics'][-1,schema['diagnostics'].index('full_target_norm_'+key)]
   error=max(error,abs(value-published))
  rec=dict(id=cid,case=c,trace_error=float(abs(np.trace(rho)-1)),hermiticity=float(np.max(abs(rho-rho.conj().T))),min_eigenvalue=float(eig.min()),
   generator_residual_fro=float(np.linalg.norm(b['L']@v)),published_final_block_error=float(np.max(abs(reduced-z['window_blocks'][-1]))),
   published_final_scalar_error=float(np.max(abs(vals.real-z['window_scalar'][-1,1:]))),full_target_norms=norms,full_norm_reconstruction_error=error,
   h_final=float(vals[b['names'].index('h')].real),source_final=float(vals[b['names'].index('source')].real))
  assert rec['trace_error']<1e-10 and rec['hermiticity']<1e-10 and rec['min_eigenvalue']>=-1e-8
  assert rec['published_final_block_error']<1e-12 and rec['published_final_scalar_error']<1e-12 and error<1e-12
  assert rec['generator_residual_fro']<1e-7
  checks.append(rec)
 # Involution: particle-hole on all nodes, spatial reflection 0<->2, edge01<->edge12.
 perm=[]
 for n in range(8):
  bits=[(n>>2)&1,(n>>1)&1,n&1];nn=(1-bits[2])*4+(1-bits[1])*2+(1-bits[0])
  for a,b,c in edges:perm.append(nn*27+int(b*9+a*3+c))
 perm=np.array(perm);assert np.array_equal(perm[perm],np.arange(216))
 pv=(perm[:,None]+216*perm[None,:]).reshape(-1,order='F')
 def find(model,target,kind):return next(x['id'] for x in checks if x['case']['model']==model and x['case']['target']==target and x['case']['kind']==kind)
 relations=[]
 for model in ('QS','RR_QS'):
  for kind in ('T','C'):
   a=find(model,'S2b',kind);b=find(model,'S1b',kind);la,lb=models[a]['L'],models[b]['L'];d=la[pv,:][:,pv]-lb
   ha=models[a]['H'][perm,:][:,perm]-models[b]['H']
   transformed_current=(models[a]['currents'][1]+models[a]['currents'][2])[perm,:][:,perm]
   current_identity=transformed_current-(models[b]['currents'][0]+models[b]['currents'][2])
   untransformed=la-lb
   ra,rb=states[a],states[b];delta=ra-rb;rd=ra[np.ix_(perm,perm)]-rb
   rec=dict(model=model,kind=kind,case_S2b=a,case_S1b=b,
    generator_covariance_max_error=float(abs(d.data).max(initial=0)),H_covariance_max_error=float(abs(ha.data).max(initial=0)),
    current_reflection_identity_error=float(abs(current_identity.data).max(initial=0)),
    generators_difference_max=float(abs(untransformed.data).max(initial=0)),states_difference_fro=float(np.linalg.norm(delta)),
    states_trace_distance=float(np.sum(abs(np.linalg.eigvalsh(delta)))/2),transformed_states_difference_fro=float(np.linalg.norm(rd)),
    cross_generator_residual_fro=float(np.linalg.norm(lb@ra.reshape(-1,order='F'))),
    window_mean_h_difference=sums[a]['reference']['h']-sums[b]['reference']['h'])
   assert rec['generator_covariance_max_error']<1e-9
   assert rec['current_reflection_identity_error']<1e-12
   assert rec['generators_difference_max']>.001
   relations.append(rec)
 elapsed=time.monotonic()-start
 out=dict(status='PASS',sample_size=len(checks),selection='10 final states only; not all full histories',checks=checks,symmetry=relations,
  runtime=dict(expected_seconds=20,lower_seconds=0,upper_seconds=180,actual_seconds=elapsed,status='PASS' if elapsed<=180 else 'INVESTIGATE'))
 (outdir/'full_state_checks.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps(dict(status=out['status'],sample_size=len(checks),symmetry=relations,runtime=out['runtime']),indent=2))
if __name__=='__main__':main(*sys.argv[1:])
