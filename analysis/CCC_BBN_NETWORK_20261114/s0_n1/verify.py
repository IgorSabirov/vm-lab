"""Read-only numerical analysis. Does not import or execute PRIMAT."""
import argparse,json,math,re
from pathlib import Path
import numpy as np
import common as c
LIGHT=('n','p','H2','H3','He3','He4','Li7','Be7')
OBS=('YPBBN','DoH','Neff','He3oH','Li7oH')
def scalar_values(r):return {**{k:r['result'][k] for k in OBS},**{'Y_'+k:r['result']['Y_final'][k] for k in LIGHT}}
def budget_for(k,p):
 b=p['numerical_budget']
 return (b[k+'_absolute'],'absolute') if k in ('YPBBN','DoH','Neff') else ((b[k+'_relative'],'relative') if k in ('He3oH','Li7oH') else (b['final_light_species_relative'],'relative'))
def delta(a,b):return {'signed':float(a-b),'absolute':float(abs(a-b)),'relative':float(abs(a-b)/max(abs(a),abs(b),1e-300))}
def differences(values,anchor):
 return {rid:{k:delta(value,values[anchor][k]) for k,value in vals.items()} for rid,vals in values.items()}
def order(q,axis,key):
 d1=float(q[1]-q[0]);d2=float(q[2]-q[1]);floor=64*np.finfo(float).eps*max(*map(abs,q),1e-300)
 state='RESOLVED';p=None
 if max(abs(d1),abs(d2))<=floor:
  state='STRUCTURALLY_UNCHANGED' if key=='Neff' and axis in ('ode','rate') else 'PLATEAU_UNRESOLVED'
 elif min(abs(d1),abs(d2))<=floor:state='REVIEW_REQUIRED'
 elif axis=='ode':
  if abs(d2)>=abs(d1):state='REVIEW_REQUIRED'
 else:
  p=float(math.log2(abs(d1/d2)))
  if d1*d2<=0 or not 0<p<=4:state='REVIEW_REQUIRED'
 return {'signed_increments':[d1,d2],'roundoff_floor':floor,'ratio':abs(d1/d2) if d2 else None,'p_observed':p,'status':state}
def read_run(root,rid):
 path=c.BASE if rid=='R0' else Path(root)/'runs'/rid
 result=c.read(path/'RESULT.json');trace=c.read(path/'TRACE.json')
 with np.load(path/'RAW_SOLVER.npz',allow_pickle=False) as f:raw={k:f[k] for k in f.files}
 manifest=c.read(path/('S0_EXECUTION_MANIFEST.json' if rid=='R0' else 'MANIFEST.json'))
 return result,trace,raw,manifest

def baryon(rid,result,raw,mass,expected):
 era_data={};prev=None
 for era in ('HT','MT','LT'):
  names=raw[era+'_species'].tolist();y=raw[era+'_Y'];t=raw[era+'_t_seconds']
  if names!=expected[era] or y.shape!=(len(names),len(t)):raise ValueError('Species/shape mismatch '+rid+era)
  if not np.isfinite(y).all() or not np.isfinite(t).all() or not np.all(np.diff(t)>0):raise ValueError('Nonfinite/nonmonotone arrays')
  weights=np.array([mass[n] for n in names]);B=weights@y
  drift=float(np.max(abs(B-B[0])));residual=float(np.max(abs(B-1)))
  if drift>1e-10 or residual>1e-10 or y.min()< -1e-12:raise ValueError('Baryon or positivity gate')
  e={'species_order':names,'B_initial_raw':float(B[0]),'B_final_raw':float(B[-1]),'integration_drift':float(B[-1]-B[0]),'max_in_era_drift':drift,'max_global_residual':residual,'raw_min':float(y.min())}
  if era=='MT':e['initial_composite_Saha_contribution']=float(sum(mass[n]*y[j,0] for j,n in enumerate(names) if n not in ('n','p')))
  era_data[era]=e
 ht,mt,lt=(era_data[e] for e in ('HT','MT','LT'))
 mtlast=dict(zip(mt['species_order'],raw['MT_Y'][:,-1]))
 if not all(v==mtlast.get(n,0.) for n,v in zip(lt['species_order'],raw['LT_Y'][:,0])):raise ValueError('Incorrect MT-LT species transfer')
 if not np.array_equal(raw['HT_Y'][:,-1],raw['MT_Y'][:2,0]):raise ValueError('HT-MT n/p transfer changed')
 final=result['result']['Y_final'];Bfinal=float(sum(mass[n]*v for n,v in final.items()))
 if not all(final[n]==max(float(v),0) for n,v in zip(lt['species_order'],raw['LT_Y'][:,-1])):raise ValueError('Unexplained final clamp')
 dHM=mt['B_initial_raw']-ht['B_final_raw'];dML=lt['B_initial_raw']-mt['B_final_raw'];post=Bfinal-lt['B_final_raw']
 decomposed=ht['B_initial_raw']-1+sum(e['integration_drift'] for e in era_data.values())+dHM+dML+post
 closure=(Bfinal-1)-decomposed
 if abs(closure)>64*np.finfo(float).eps:raise ValueError('Baryon decomposition corrupted')
 if abs(dHM-mt['initial_composite_Saha_contribution'])>64*np.finfo(float).eps:raise ValueError('Saha contribution mismatch')
 return {'eras':era_data,'handoffs':{'HT_to_MT':{'B_before_raw':ht['B_final_raw'],'B_after_raw':mt['B_initial_raw'],'delta_B':dHM,'composite_Saha_sum_A_Y':mt['initial_composite_Saha_contribution'],'renormalized':False},'MT_to_LT':{'B_before_raw':mt['B_final_raw'],'B_after_raw':lt['B_initial_raw'],'delta_B':dML,'species_mapping_verified':True}},'postprocessing':{'B_LT_final_raw':lt['B_final_raw'],'B_final_reported':Bfinal,'clamp_and_zero_fill_delta_B':post},'closure':{'initial_B_minus_one':ht['B_initial_raw']-1,'decomposed_final_B_minus_one':decomposed,'direct_final_B_minus_one':Bfinal-1,'decomposition_roundoff_residual':closure}}
def analyze(root):
 root=Path(root);pre=c.read(c.PKG/'N1_PREREGISTRATION.json');c.verify_freeze(root);hash_count=c.verify_artifacts(root)
 ids=['R0','R_ENV']+['R'+str(i) for i in range(1,9)]+['R_NET_AMAX8'];runs={i:read_run(root,i) for i in ids};freeze=c.read(root/'CACHE_FREEZE.json')
 mass=runs['R1'][3]['mass_numbers']
 for n,a in mass.items():
  expected=1 if n in ('n','p') else int(re.search(r'\d+$',n).group())
  if a!=expected:raise ValueError('Mass number mismatch')
 baryons={};trajectories={};values={};cache_checks={}
 for rid,(r,t,raw,m) in runs.items():
  if r['status']!='ENGINEERING_PASS':raise ValueError('Incomplete run '+rid)
  expected={e:raw[e+'_species'].tolist() for e in ('HT','MT','LT')} if rid=='R0' else {e:m['network'][e] for e in ('HT','MT','LT')}
  baryons[rid]=baryon(rid,r,raw,mass,expected);values[rid]=scalar_values(r)
  yf=r['result']['Y_final']
  if abs(4*yf['He4']-r['result']['YPBBN'])>1e-15 or abs(yf['H2']/yf['p']-r['result']['DoH'])>1e-19:raise ValueError('Observable reconstruction failed')
  if rid=='R0':continue
  group=c.row_for(rid)['cache_group'];f=freeze['groups'][group]
  if r['cache_before']!=f['overlay'] or r['cache_after']!=f['overlay']:raise ValueError('Cache mismatch')
  for info in f['weak_files'].values():
   if r['loaded_files'].get(info['source'])!=info['identity']:raise ValueError('Cache load identity mismatch')
  if c.environment_signature(m['environment'])!=c.read(root/'TARGET_ENVIRONMENT.json')['signature']:raise ValueError('Unmatched worker environment')
  if m['config']!=c.read(root/'RESOLVED_CONFIGS.json')[rid]:raise ValueError('Run config mismatch')
  if m['source_commit']!=c.read(root/'SOURCE_FREEZE.json')['commit'] or m['upstream_commit']!=c.PIN:raise ValueError('Run source mismatch')
  cache_checks[rid]='CACHE_INTEGRITY_PASS'
  trajectories[rid]={}
  for base,cur in zip(runs['R_ENV'][1]['eras'],t['eras']):
   if base['era']!=cur['era'] or not np.array_equal(base['T_MeV'],cur['T_MeV']):raise ValueError('Not aligned in temperature')
   metrics={}
   for n in set(base['species'])&set(cur['species']):
    x=np.array(base['Y'])[:,base['species'].index(n)];y=np.array(cur['Y'])[:,cur['species'].index(n)];d=abs(y-x);j=int(np.argmax(d));norm=max(float(abs(x).max()),float(abs(y).max()),1e-30)
    metrics[n]={'max_absolute':float(d[j]),'normalized_max':float(d[j]/norm),'T_MeV':cur['T_MeV'][j],'denominator':norm}
   trajectories[rid][cur['era']]=metrics
 axes={axis:{k:order([values[r][k] for r in runs3],axis,k) for k in values['R0']} for axis,runs3 in {'ode':['R_ENV','R1','R2'],'rate':['R_ENV','R3','R4'],'background':['R_ENV','R5','R6']}.items()}
 gates={}
 pairs=[(r,'R_ENV') for r in ('R2','R4','R6','R8')]+[('R2','R1'),('R4','R3'),('R6','R5'),('R8','R7')]
 for a,b in pairs:
  gates[a+'_vs_'+b]={}
  for k in values['R0']:
   bound,kind=budget_for(k,pre);d=delta(values[a][k],values[b][k]);gates[a+'_vs_'+b][k]={'value':d[kind],'limit':bound,'metric':kind,'pass':d[kind]<=bound}
 hard=all(g['pass'] for pair in gates.values() for g in pair.values());review=any(g['status'] not in ('RESOLVED','STRUCTURALLY_UNCHANGED') for axis in axes.values() for g in axis.values())
 status='NUMERICAL_CONVERGENCE_FAIL' if not hard else ('INCONCLUSIVE' if review else 'NUMERICAL_CONVERGENCE_PASS')
 interactions={level:{k:float(values[joint][k]-values['R_ENV'][k]-sum(values[i][k]-values['R_ENV'][k] for i in singles)) for k in values['R0']} for level,joint,singles in [('medium','R7',['R1','R3','R5']),('fine','R8',['R2','R4','R6'])]}
 out={'schema':'vm-lab-s0-n1-convergence-summary-v1','status':status,'engineering_status':'ENGINEERING_PASS','cache_status':'CACHE_INTEGRITY_PASS','stability_status':'NUMERICAL_STABILITY_PASS' if hard else 'NUMERICAL_STABILITY_FAIL','scientific_acceptance':False,'artifact_hashes_verified':hash_count,'primary_anchor':'R_ENV','observables':values,'differences_from_anchor':differences(values,'R_ENV'),'differences_from_R0':{rid:{k:delta(v,values['R0'][k]) for k,v in vals.items()} for rid,vals in values.items()},'axes':axes,'joint_interactions':interactions,'gates':gates,'trajectory_metrics':trajectories,'interpretation':{'fixed_atol_only':True,'primary_comparisons_use_matched_R_ENV':True,'independent_solver':False,'physical_uncertainty_propagated':False,'roundoff_plateau_is_not_proof_of_convergence':True}}
 environment_comparison={k:{**delta(values['R_ENV'][k],values['R0'][k]),'limit':budget_for(k,pre)[0],'metric':budget_for(k,pre)[1],'within_budget':delta(values['R_ENV'][k],values['R0'][k])[budget_for(k,pre)[1]]<=budget_for(k,pre)[0]} for k in values['R0']}
 out['environment_status']='ENVIRONMENT_DISPLACEMENT_WITHIN_BUDGET' if all(x['within_budget'] for x in environment_comparison.values()) else 'ENVIRONMENT_SENSITIVITY_REVIEW_REQUIRED'
 c.write(root/'ENVIRONMENT_COMPARISON.json',{'status':out['environment_status'],'comparisons':environment_comparison,'primary_anchor':'R_ENV','historical_reference':'R0','scientific_acceptance':False})
 c.write(root/'CONVERGENCE_SUMMARY.json',out)
 c.write(root/'BARYON_BUDGET.json',{'schema':'vm-lab-s0-n1-baryon-budget-v1','mass_numbers_source':'pinned_PRIMAT_cfg.Nuclides cross-checked against isotope labels','renormalization_applied':False,'runs':baryons})
 full=runs['R_ENV'][0]['result']['Y_final'];small=runs['R_NET_AMAX8'][0]['result']['Y_final'];shared=set(runs['R_ENV'][2]['LT_species'])&set(runs['R_NET_AMAX8'][2]['LT_species'])
 comp={n:delta(full[n],small[n]) for n in sorted(shared)}
 c.write(root/'NETWORK_COMPARISON.json',{'status':'SAME_SOLVER_NETWORK_COMPARISON','shared_species':comp,'reference_relative_tolerance':1e-4,'within_reference':all(d['relative']<=1e-4 for d in comp.values()),'independent_solver':False,'scientific_acceptance':False})
 summary=['# S0-N1 result','',f'Engineering: **ENGINEERING_PASS**. Cache: **CACHE_INTEGRITY_PASS**. Numerical outcome: **{status}**.', '',f'Stability budgets: **{out["stability_status"]}**. Fixed absolute tolerances; no scientific acceptance.','', '| Run | Yp | D/H | Neff |','|---|---:|---:|---:|']
 for rid in ids:summary.append(f'| {rid} | {values[rid]["YPBBN"]:.16g} | {values[rid]["DoH"]:.16g} | {values[rid]["Neff"]:.16g} |')
 summary+=['','All raw data, per-era baryon decomposition, axis order flags, joint residuals and trajectory comparisons are in the adjacent JSON artifacts. A failed numerical budget is a measured numerical result, not a failed physical model. INCONCLUSIVE preserves unresolved order/atol questions; thresholds were not changed after observing results.']
 (root/'REPORT.md').write_text('\n'.join(summary)+'\n')
 return out
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('root');a=ap.parse_args();out=analyze(a.root);print(json.dumps({k:out[k] for k in ('status','engineering_status','stability_status','cache_status')}))
