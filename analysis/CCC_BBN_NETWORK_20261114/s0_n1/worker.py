"""Isolated cache builder/probe/solver. Does not modify P2 or PRIMAT source."""
import argparse,os,sys,time,resource,shutil
from pathlib import Path
import common as c

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--upstream',required=True);ap.add_argument('--root',required=True);ap.add_argument('--run-id',required=True)
 a=ap.parse_args();root=Path(a.root).resolve();up=Path(a.upstream).resolve();rid=a.run_id
 source=c.verify_freeze(root);tree=c.check_upstream(up);row=c.row_for(rid);group=row['cache_group']
 cache=root/'caches'/group;out=root/'runs'/rid;out.mkdir(parents=True,exist_ok=False);cache.mkdir(parents=True,exist_ok=True)
 started=time.monotonic();building=rid.startswith('CACHE_')
 if c.environment_signature(c.env())!=c.read(root/'TARGET_ENVIRONMENT.json')['signature']:raise RuntimeError('Worker environment differs from the matched target anchor')
 sys.path.insert(0,str(up))
 import numpy as np
 from scipy.integrate._ivp.bdf import BDF
 from primat.config import PRIMATConfig,DEFAULT_PARAMS
 from primat.cache_utils import fingerprint_hash,resolve_cache_file,write_cache_with_fingerprint
 from primat.weak_rates.cache import weak_rate_fingerprint,thermal_fingerprint
 import primat.weak_rates.api as api
 import primat.weak_rates.corrections as corrections
 import primat.nuclear_network as nuclear
 from primat.main import PRIMAT
 params=c.config_for(rid,cache);cfg=PRIMATConfig(params)
 resolved={k:getattr(cfg,k) for k in DEFAULT_PARAMS};baseline=c.read(c.BASE/'S0_EXECUTION_MANIFEST.json')['resolved_defaults']
 allowed=set(c.AXES)|{'cache_dir'}|({'amax'} if rid=='R_NET_AMAX8' else set())
 for k,v in resolved.items():
  if k not in allowed and (type(v)!=type(baseline[k]) or v!=baseline[k]):raise RuntimeError('Non-matrix config changed: '+k)
 expected=c.read(root/'RESOLVED_CONFIGS.json')[rid]
 public={**params,'cache_dir':'N1_CACHE/'+group}
 if public!=expected:raise RuntimeError('Run config differs from preflight')
 weak=fingerprint_hash(weak_rate_fingerprint(cfg));thermal=fingerprint_hash(thermal_fingerprint(cfg))
 if thermal!='cfdb4d324bb5651f':raise RuntimeError('Thermal cache identity changed')
 files={name:Path(resolve_cache_file(cfg,'weak',name)).resolve() for name in ['nTOp_'+weak+'.txt','nTOp_thermal_'+thermal+'.txt']}
 th=files['nTOp_thermal_'+thermal+'.txt']
 if c.digest(th)['git_blob_sha']!='e3a8b6782393df73a9140e05bd3941ff135af2c9':raise RuntimeError('Thermal bytes changed')
 before=c.snapshot(cache);loaded={};original_load=np.loadtxt
 def load(fname,*args,**kw):
  if isinstance(fname,(str,Path)) and Path(fname).is_file():
   f=Path(fname).resolve();label=('PRIMAT/'+str(f.relative_to(up))) if f.is_relative_to(up) else ('N1_CACHE/'+group+'/'+str(f.relative_to(cache)))
   loaded[label]=c.digest(f)
  return original_load(fname,*args,**kw)
 np.loadtxt=load
 original_compute=api.ComputeWeakRates;computed=[]
 def compute(*args,**kw):
  if not building or group=='BG2000' or computed:raise RuntimeError('Unapproved weak recomputation')
  computed.append(weak);return original_compute(*args,**kw)
 api.ComputeWeakRates=compute
 def forbidden(*args,**kw):raise RuntimeError('Thermal CCRTh recomputation forbidden')
 corrections._L_CCRTh_compute=forbidden
 freeze=None
 if not building:
  freeze=c.read(root/'CACHE_FREEZE.json')['groups'][group]
  if before!=freeze['overlay']:raise RuntimeError('Cache mutation before solve')
  for name,p in files.items():
   if not p.is_file() or c.digest(p)!=freeze['weak_files'][name]['identity']:raise RuntimeError('Frozen weak cache mismatch')
 init=time.monotonic();run=PRIMAT(params);init_seconds=time.monotonic()-init
 expected_count=(12,67) if rid=='R_NET_AMAX8' else (59,428)
 if (len(run.nucl._lt_net.species),len(run.nucl._lt_net.names))!=expected_count:raise RuntimeError('Network inventory mismatch')
 if c.digest(th)['git_blob_sha']!='e3a8b6782393df73a9140e05bd3941ff135af2c9':raise RuntimeError('Thermal mutation')
 def source_label(p):return 'PRIMAT/'+str(p.relative_to(up)) if p.is_relative_to(up) else 'N1_CACHE/'+group+'/'+str(p.relative_to(cache))
 manifest={'run_id':rid,'source_commit':source['commit'],'preregistration_sha256':c.digest(c.PKG/'N1_PREREGISTRATION.json')['sha256'],
  'upstream_commit':c.PIN,'upstream_tree':tree,'config':public,'resolved_defaults':{**resolved,'cache_dir':'N1_CACHE/'+group},
  'fingerprints':{'weak':weak,'thermal':thermal},'environment':c.env(),'network':{'HT':['n','p'],'MT':list(run.nucl._mt_net.species),'LT':list(run.nucl._lt_net.species),'MT_channels':list(run.nucl._mt_net.names),'LT_channels':list(run.nucl._lt_net.names)},
  'mass_numbers':{n:int(sum(cfg.Nuclides[n])) for n in cfg.Nuclides},'scientific_acceptance':False}
 c.write(out/'MANIFEST.json',manifest)
 if building:
  # Generator closure audit at unchanged BG2000, using no table for a solve.
  regeneration=None
  if group=='BG2000':
   bg=run.background
   generated=np.column_stack(original_compute([bg.Tg_vec,bg.Tnue_vec],cfg,dFDneu_func=bg.dFDneu_func,dFDneu_moments=bg.dFDneu_moments))
   shipped=original_load(files['nTOp_'+weak+'.txt'])
   if generated.shape!=shipped.shape:raise RuntimeError('BG2000 reconstruction shape mismatch')
   norm=np.maximum(np.maximum(abs(generated),abs(shipped)),1e-28)
   delta=abs(generated-shipped);relative=delta/norm
   regeneration={'max_normalized_difference':float(relative.max()),'rtol':1e-10,'absolute_tolerance':1e-26,'pass':bool(np.all(delta<=1e-10*np.maximum(abs(generated),abs(shipped))+1e-26)),'method':'Direct pinned ComputeWeakRates on initialized BG2000; shipped cache remains sole solve input'}
   c.write(out/'GENERATOR_CLOSURE.json',regeneration)
   np.savez_compressed(out/'GENERATED_WEAK.npz',table=generated,shipped=shipped)
   if not np.isfinite(generated).all():raise RuntimeError('Nonfinite generated table')
   target=root/'caches/BG2000_GEN';target.mkdir(parents=True,exist_ok=False)
   if not write_cache_with_fingerprint(str(target/'weak'/('nTOp_'+weak+'.txt')),weak_rate_fingerprint(cfg),generated.T,col_header='T[K] Gamma_nTOp[1/tau_n] Gamma_pTOn[1/tau_n]'):raise RuntimeError('Generated table write failed')
   shutil.copytree(cache/'plasma',target/'plasma')
   regeneration['disposition']='Measured discrepancy retained; separate R_CACHE uses generated BG2000 as primary anchor, R_ENV retains shipped bytes'
   c.write(out/'GENERATOR_CLOSURE.json',regeneration)
  elif group=='BG2000_GEN':
   if computed:raise RuntimeError('Generated BG2000 must load preserved builder table')
  elif len(computed)!=1:raise RuntimeError('Expected exactly one newly generated weak table')
  after=c.snapshot(cache)
  allowed_files={'plasma/electron_thermo_45b89f3e1b24e961.txt'}
  if group!='BG2000':allowed_files.add('weak/nTOp_'+weak+'.txt')
  if set(after)!=allowed_files:raise RuntimeError('Unexpected cache files: '+str(set(after)))
  files={n:Path(resolve_cache_file(cfg,'weak',n)).resolve() for n in files}
  data={'status':'CACHE_BUILD_PASS','group':group,'overlay':after,'weak_files':{n:{'source':source_label(p),'identity':c.digest(p)} for n,p in files.items()},
   'loaded':loaded,'initialization_seconds':init_seconds,'wall_seconds':time.monotonic()-started,'generator_closure':regeneration,'scientific_acceptance':False}
  c.check_upstream(up);c.write(out/'RESULT.json',data);return
 # Observe solver calls without changing methods, tolerances, RHS or states.
 originals=nuclear.solve_ivp;sols=[];eras=[];traces=[];raw={}
 baseline_trace=c.read(c.BASE/'TRACE.json')['eras']
 def capture(fun,t_span,y0,*args,**kw):
  era=('HT','MT','LT')[len(sols)];idx=len(sols);kw['dense_output']=True
  rt=cfg.numerical_precision*(10 if era=='LT' else 1);at={'HT':1e-10,'MT':1e-15,'LT':1e-26}[era]
  if kw['rtol']!=rt or kw['atol']!=at:raise RuntimeError('Unexpected effective tolerances')
  method=kw['method'];family='LSODA' if method=='LSODA' else ('BDF' if method=='BDF' or (isinstance(method,type) and issubclass(method,BDF)) else 'unknown')
  if family!=('LSODA' if era=='HT' else 'BDF'):raise RuntimeError('Unexpected solver method')
  t0=time.monotonic();sol=originals(fun,t_span,y0,*args,**kw);elapsed=time.monotonic()-t0;sols.append(sol)
  species=manifest['network'][era];mass=np.array([manifest['mass_numbers'][n] for n in species])
  raw[era+'_t_seconds']=sol.t;raw[era+'_Y']=sol.y;raw[era+'_species']=np.asarray(species)
  np.savez_compressed(out/('RAW_'+era+'.npz'),t=sol.t,Y=sol.y,species=np.asarray(species))
  T=np.asarray(baseline_trace[idx]['T_MeV']);times=np.asarray(run.background.t_of_T(T))
  overshoot=max(float(sol.t[0]-times[0]),float(times[-1]-sol.t[-1]),0)
  if overshoot>1e-9*max(abs(sol.t[-1]),1):raise RuntimeError('Common temperature grid outside solver interval')
  times=np.clip(times,sol.t[0],sol.t[-1]);Y=sol.sol(times)
  e={'era':era,'success':bool(sol.success),'status':int(sol.status),'message':str(sol.message),'method_family':family,'method':method if isinstance(method,str) else method.__name__,
   'rtol':float(kw['rtol']),'atol':float(kw['atol']),'nfev':int(sol.nfev),'njev':int(sol.njev),'nlu':int(sol.nlu),'steps':int(len(sol.t)),
   'solver_seconds':elapsed,'max_baryon_residual':float(np.max(abs(mass@sol.y-1))),'in_era_baryon_drift':float(np.max(abs(mass@sol.y-mass@sol.y[:,0]))),
   'raw_min':float(sol.y.min()),'boundary_time_clipping_seconds':overshoot}
  eras.append(e);traces.append({'era':era,'species':species,'T_MeV':T.tolist(),'t_seconds':times.tolist(),'Y':Y.T.tolist()})
  c.write(out/('ERA_'+era+'.json'),e);c.write(out/('TRACE_'+era+'.json'),traces[-1])
  if not sol.success or not np.isfinite(sol.y).all() or not np.all(np.diff(sol.t)>0) or not np.isfinite(Y).all():raise RuntimeError('Invalid era output')
  if e['max_baryon_residual']>1e-10 or e['in_era_baryon_drift']>1e-10 or e['raw_min']< -1e-12:raise RuntimeError('Conservation/positivity gate failed')
  return sol
 nuclear.solve_ivp=capture
 result=run.solve(progress=False)
 if len(sols)!=3:raise RuntimeError('Missing era')
 final={n:float(v) for n,v in run.nuclear.Y_final.items()};result['Y_final']=final
 if any(not np.isfinite(v) or v<0 for v in final.values()):raise RuntimeError('Invalid final output')
 if any(final[n]!=max(float(v),0) for n,v in zip(manifest['network']['LT'],sols[-1].y[:,-1])):raise RuntimeError('Unexplained final state postprocessing')
 after=c.snapshot(cache)
 if after!=before:raise RuntimeError('Cache mutated during solve')
 for name,info in freeze['weak_files'].items():
  if loaded.get(info['source'])!=info['identity']:raise RuntimeError('Frozen weak file not observed loaded')
 for rel,identity in freeze['overlay'].items():
  if loaded.get('N1_CACHE/'+group+'/'+rel)!=identity:raise RuntimeError('Frozen overlay file not observed loaded')
 np.savez_compressed(out/'RAW_SOLVER.npz',**raw)
 c.write(out/'TRACE.json',{'eras':traces,'coordinate':'same R0 temperature points'})
 c.write(out/'RESULT.json',{'run_id':rid,'status':'ENGINEERING_PASS','result':result,'eras':eras,'loaded_files':loaded,'cache_before':before,'cache_after':after,
  'timing':{'initialization_seconds':init_seconds,'wall_seconds':time.monotonic()-started,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024},'scientific_acceptance':False})
 c.check_upstream(up)
if __name__=='__main__':main()
