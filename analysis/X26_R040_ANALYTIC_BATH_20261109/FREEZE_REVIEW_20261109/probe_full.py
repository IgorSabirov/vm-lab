"""Small local counterexamples; synthetic inputs only, no VM authorization."""
import json,pathlib,sys,copy,hashlib,importlib.util
import numpy as np
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--package',type=pathlib.Path,required=True);ap.add_argument('--carrier',type=pathlib.Path,required=True);ap.add_argument('--outdir',type=pathlib.Path,required=True);args=ap.parse_args()
R=args.outdir.resolve();R.mkdir(parents=True,exist_ok=True);P=args.package.resolve();sys.path.insert(0,str(P))
from x26r040 import add_mapping as am
from x26r040.integrated import preflight_full_pipeline,_loading_from_manifest,run_full_pipeline
from x26r040.model import R040Parameters
from x26r040.thermal_loading import bright_bohr_transition,simulate_davies_loading
from x26r040.resource_ledger import evaluate_resource_ledger
from x26r040.transfer import check_moving_projector_transport,projector_from_dark_vector,validate_orthogonal_projector
out={}
checks=[]
for line in (P/'SHA256SUMS.txt').read_text().splitlines():
 h,n=line.split(maxsplit=1);checks.append(hashlib.sha256((P/n).read_bytes()).hexdigest()==h)
out['full_archive']={'sha256':'5ec1a9755a8e29d755c3e5df175b1889324301d253df6e0241bc47dccfa37564','checksum_count':len(checks),'all_checksums_match':all(checks)}
carrier=args.carrier.resolve(); c=am.load_verified_carrier(carrier)
def true_k(w):
 a,b,ab,c,d,cd=[sum((s & mask)==v for s in w) for mask,v in [(5,1),(5,4),(5,5),(10,2),(10,8),(10,10)]]
 return [a*c,b*d]
out['K_counterexample']=[]
for w in ([5,10],[9,6]):
 cur=w[:];lens=[]
 for _ in range(8):lens.append(len(cur));cur=c.full_step(cur)[0]
 out['K_counterexample'].append({'word':w,'patch_K':[am.combinatorial_invariants(w)[k] for k in ['K1','K2']],'pure_half_K':true_k(w),'lengths_first_8':lens})
m=json.loads((P/'configs/X26_ADD_R040_LOADING.template.json').read_text());m['carrier'].update(path=str(carrier),word=[5,10,0,0],anchors={'V':0,'1':1,'2':2})
m['phi'].update(accepted=True,assumption='LOCAL TEST ONLY')
m['loading']['psi'].update(accepted=True,mode='COHERENT_EVENT_TRIGGERED');m['loading']['resource_model']['accepted']=True;m['transfer'].update(accepted=True,operator_real_imag=np.stack([np.eye(3),np.zeros((3,3))],axis=-1).tolist())
out['false_ready_preflight']=preflight_full_pipeline(m)
out['false_ready_preflight']['still_missing']=['phi.radius','phi coefficients','initial state','time grid','resource conversions','nested spectral freeze/runtime']
p=R040Parameters(.2,.2,.1,.15,.3,.3,1.,.22)
m['loading']['psi'].update(radius=0,activity_scale=1.,initial_state_real_imag=[[0,0],[0,0],[1,0]],times=[0.,.5,1.],duration=1.,coupling_strength=.2)
try:_loading_from_manifest(p,[0,0,0],{'V':0,'1':1,'2':2},[1,0,0],{'V':0,'1':1,'2':2},m);out['template_loading_field_path']='unexpected success'
except Exception as e:out['template_loading_field_path']={'exception':type(e).__name__,'message':str(e)}
b=bright_bohr_transition(p)['bright_vector'];t=np.linspace(0,2,101)
th=simulate_davies_loading(p,b,t,2.,.3,1.,lambda x:np.sin(np.pi*x/2)**2,'synthetic_test_bath')
try:json.dumps(th,allow_nan=False);out['thermal_json']='success'
except Exception as e:out['thermal_json']={'exception':type(e).__name__,'message':str(e),'location':'bohr_transition vectors contain Python complex values'}
out['thermal_algebra_checks']={'max_trace_error':max(abs(x['real']-1)+abs(x['imag']) for x in th['density_matrix_trace']),'minimum_eigenvalue':min(th['minimum_density_eigenvalue']),'first_law_residual':th['system_energy_model_units'][-1]-th['system_energy_model_units'][0]+th['reservoir_heat_gained_model_units'],'minimum_entropy_production':min(s-th['system_von_neumann_entropy_nats'][0]+2.*(th['system_energy_model_units'][0]-e) for s,e in zip(th['system_von_neumann_entropy_nats'],th['system_energy_model_units']))}
rm={'source':'MODEL_ASSUMPTION','accepted':True,'assumption':'LOCAL TEST ONLY','fuel_units_available':100,'energy_per_fuel_unit_model_units':1.,'drive_efficiency':1.,'actuator_switch_energy_model_units':0.,'controller_reset_bits':1.,'k_B_model_units_per_temperature':1.,'temperature_model_units':1.,'precursor_units_available':1,'precursor_units_per_activation':0.,'initial_packet_preparation_energy_model_units':0.}
ledger=evaluate_resource_ledger({'status':'synthetic','external_work_input_model_units':0.},rm)
out['reset_bound_used_for_feasibility']={'status':ledger['status'],'fuel_required':ledger['fuel_units_required'],'note':'Only Landauer lower bound supplied; actual finite-time reset work not provided'}
# Same algebra checks on the full delivered module.
pr=np.diag([1.,0.,0.]);qr=np.diag([0.,1.,0.]);out['infinite_tolerance_status']=check_moving_projector_transport(pr,qr,2*np.eye(3),tol=float('inf'))['status']
bad=projector_from_dark_vector(np.array([1.000005,0.,0.]));out['projector_constructor_idempotence_error']=float(np.linalg.norm(bad@bad-bad))
# Complete only a synthetic local fixture, explicitly not a frozen scientific manifest.
spec=importlib.util.spec_from_file_location('fixture',P/'tests/test_pipeline.py');fx=importlib.util.module_from_spec(spec);spec.loader.exec_module(fx)
m['spectral']=fx.synthetic_manifest();m['phi'].update(radius=0,E_pair_0=.2,E_2_0=.1,lambda_pair=.2,lambda_2=.1,t0=.3,barrier_0=0.,barrier_contrast=1.,alpha=1.,kappa=1.,g=.22)
m['loading']['initial_state_real_imag']=[[float(z.real),float(z.imag)] for z in p.bright_vector];m['loading']['times']=t.tolist();m['loading']['resource_model']=rm
# Duration=1 whereas output times extend to2: intentional post-pulse readout only.
report=run_full_pipeline(m)
def complex_paths(o,path=''):
 if isinstance(o,complex):return [path]
 if isinstance(o,dict):return [p for k,v in o.items() for p in complex_paths(v,path+'/'+str(k))]
 if isinstance(o,list):return [p for i,v in enumerate(o) for p in complex_paths(v,path+'/'+str(i))]
 return []
out['integrated_json_complex_paths']=complex_paths(report)
try: json.dumps(report,allow_nan=False);out['integrated_json_status']='success'
except TypeError as e:out['integrated_json_status']=str(e)
out['integrated_synthetic_execution']={'executed':True,'loading_status':report['loading']['status'],'has_permutation_control':any('permutation' in k for k in report),'spectral_before_only':('spectral_only' in report and 'spectral_after' not in report),'post_transfer_loaded_density_present':any('state_after_transfer' in k for k in report),'technical_status_aggregate_present':('technical_checks' in report),'transfer_status':report['moving_projector_transfer']['status']}
(R/'FULL_REVIEW_CHECKS.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n');print(json.dumps(out,indent=2))
