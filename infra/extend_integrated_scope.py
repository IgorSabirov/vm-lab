"""Prospective candidate-0.3 manifest generation; no simulation or fitted thresholds."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'experiments/now_integrated_v1/preregistration'
read=lambda n:json.loads((P/(n+'.json')).read_text())
def write(n,d):(P/(n+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
cases,plan,mapping=read('CASES'),read('PROTOCOL'),read('IMPLEMENTATION_MAP')
cases['cases']=[c for c in cases['cases'] if not c['id'].startswith('full_')]
cases['contrasts']=[c for c in cases['contrasts'] if not c['id'].startswith('full_')]
base=dict(separate_apparatus=True,inherited_routes=True,forced_content=[1,1],donor_precursor=30)
def add(name,**delta):
 cfg=dict(base,**delta)
 cases['cases'].append(dict(id='full_'+name,config=cfg,stage='IMPLEMENTED_NOT_EXECUTED',sampling_mode='deterministic' if cfg.get('memory','classical')=='classical' and cfg.get('forced_content') is not None else 'seed_ensemble'))
add('base')
for name,delta in dict(no_production=dict(production=False),no_contact=dict(repair_contacts=False),neither=dict(production=False,repair_contacts=False),no_writer=dict(seed_writer=False),no_reader=dict(seed_reader=False),writer_damage=dict(damage_writer=True),reader_damage=dict(damage_reader=True),no_record=dict(erase_record=True),no_apparatus=dict(transfer_apparatus=False),scramble=dict(scramble_child=True),scramble_no_apparatus=dict(scramble_child=True,transfer_apparatus=False),no_route=dict(transmit_route=False),route_damage=dict(damage_route=True),no_template_bank=dict(template_slots=0),imported_contact=dict(imported_contacts=True),removed_parent_template=dict(remove_parent_template_after_transfer=True),late_resource=dict(supply_delay=100),late_record=dict(record_delay=100),moving=dict(receiver_velocity=.3),fragments=dict(fragmented_records=True),fragment_duplicate=dict(fragmented_records=True,duplicate_fragment=True),fragment_lost=dict(fragmented_records=True,drop_fragment=True),fragment_zero=dict(fragmented_records=True,fragment_slots=0),fragment_expiry=dict(fragmented_records=True,inbox_lifetime=.1),branch=dict(branching=True,donor_fuel=64),branch_weak=dict(branching=True,donor_fuel=20)).items():add(name,**delta)
for apparatus in (False,True):
 for mark in (False,True):add('seed_'+str(int(apparatus))+str(int(mark)),initiator_enabled=False,initial_seed=apparatus,prepared_records=mark)
for mode in ('V1','V2','A'):add('law_'+mode,seed_writer=False,prepared_records=True,production_semantics=mode)
for mode in ('erase','trace','isolate','transfer','decay'):add('completion_'+mode,completion_mode=mode,completion_probe=True)
for role in ('writer','reader'):add('cycles_'+role,donor_fuel=160,donor_precursor=80,repair_rounds=2,cycle_damage_role=role)
add('cycles_no_production',donor_fuel=160,donor_precursor=80,repair_rounds=2,production=False)
add('cycles_no_contact',donor_fuel=160,donor_precursor=80,repair_rounds=2,repair_contacts=False)
for name,damage,repair in [('transport_intact',False,True),('transport_patch',True,True),('transport_unrepaired',True,False)]:
 add(name,donor_fuel=100,donor_precursor=60,read_wait=64,transport_support=True,damage_transport=damage,repair_transport=repair)
for preparation in ('correlated','independent','bell_x','dephased_x','bell_z','dephased_z'):add(preparation,forced_content=None,preparation=preparation)
for memory in ('finite_dark','finite_static'):
 for wait in (16,32,64):add(memory+'_'+str(wait),memory=memory,read_wait=wait)
for modes in (4,16,32):add('bath_'+str(modes),memory='finite_static',bath_modes=modes)
add('wave_no_transfer',memory='finite_dark',transfer_apparatus=False)
add('wave_delayed',memory='finite_static',record_delay=16)
add('wave_moving',memory='finite_static',receiver_velocity=.3)
links={f'X{i:02}':dict(contrasts=[],controls=[]) for i in range(1,17)}
def contrast(design,name,names,metric='final_function',weights=None,equal=True):
 identity='full_'+name
 cases['contrasts'].append(dict(id=identity,cases=['full_'+x for x in names],weights=weights or [1,-1],metric=metric,require_equal_initial_totals=equal,question=design,interpretation='Prospective bounded common-engine comparison; outcome is not a physical realization or closure theorem.'))
 links[design]['contrasts'].append(identity)
contrast('X01','seed_mark',['seed_11','seed_10','seed_01','seed_00'],weights=[1,-1,-1,1])
contrast('X02','V2_V1',['law_V2','law_V1'],'child_function')
contrast('X02','A_V1',['law_A','law_V1'],'child_function')
for mode in ('erase','trace','transfer','decay'):contrast('X03','completion_'+mode,['completion_'+mode,'completion_isolate'])
contrast('X03','erased_record',['base','no_record'])
contrast('X04','record_apparatus',['base','scramble','no_apparatus','scramble_no_apparatus'],weights=[1,-1,-1,1])
contrast('X05','resource_delivery',['base','late_resource'])
contrast('X06','route_inheritance',['base','no_route'])
contrast('X06','route_damage',['base','route_damage'])
contrast('X06','template_bank',['base','no_template_bank'])
contrast('X06','imported_contacts',['imported_contact','base'])
contrast('X07','writer_replacement',['base','writer_damage'])
contrast('X07','reader_absent',['base','reader_damage'])
contrast('X07','repeat_writer',['cycles_writer','cycles_no_production'],'parent_function')
contrast('X07','repeat_reader',['cycles_reader','cycles_no_contact'],'parent_function')
contrast('X07','transport_repair',['transport_patch','transport_unrepaired'],'child_function')
contrast('X07','transport_damage',['transport_intact','transport_patch'],'child_function')
contrast('X08','classical_joint',['correlated','independent'])
contrast('X08','quantum_XX',['bell_x','dephased_x'])
contrast('X08','quantum_ZZ',['bell_z','dephased_z'])
for name,metric in [('threshold','final_function'),('health','mean_health')]:
 contrast('X09','interaction_'+name,['base','no_production','no_contact','neither'],metric,weights=[1,-1,-1,1])
for wait in (16,32,64):contrast('X10','load_cycle_'+str(wait),['finite_dark_'+str(wait),'finite_static_'+str(wait)])
contrast('X10','grid_16_32',['bath_16','bath_32'])
contrast('X10','grid_4_16',['bath_4','bath_16'])
contrast('X10','delay_memory',['finite_static_32','wave_delayed'])
contrast('X11','same_response',['finite_dark_32','wave_no_transfer'])
contrast('X14','physical_motion',['base','moving'])
contrast('X14','wave_motion',['finite_static_32','wave_moving'])
contrast('X15','branch_budget',['branch','branch_weak'],equal=False)
contrast('X15','fragment_replay',['fragments','fragment_duplicate'])
contrast('X15','fragment_loss',['fragments','fragment_lost'])
contrast('X15','fragment_capacity',['fragments','fragment_zero'])
contrast('X15','fragment_ttl',['fragments','fragment_expiry'])
contrast('X16','parent_template_removed',['base','removed_parent_template'],'child_function')
plan['design_controls']=[]
for identity,kind,design,delta in [
 ('v1_support','v1_support','X02',{}),('joint_measurements','joint_instrument','X08',{}),
 ('readout_classical','readout','X10',{}),('readout_wave','readout','X10',dict(memory='finite_static')),
 ('full_cut','internal_slice','X12',{}),('fragment_cut','internal_slice','X12',dict(fragmented_records=True)),
 ('wave_cut','internal_slice','X12',dict(memory='finite_static')),
 ('selection','boundary_selection','X13',dict(forced_content=None)),
 ('coordinate_order','foliation','X14',{}),('moving_coordinate_order','foliation','X14',dict(receiver_velocity=.3)),
 ('branch_coordinate_order','foliation','X15',dict(branching=True,donor_fuel=64))]:
 plan['design_controls'].append(dict(id=identity,kind=kind,design_ids=[design],config=dict(base,**delta),phases=['smoke','calibrate','main']))
 links[design]['controls'].append('control::'+identity)
for i in mapping['comparisons']:
 i['previous_candidate']=dict(implementation_status=i['implementation_status'],limit=i['limit']) if 'previous_candidate' not in i else i['previous_candidate']
 i.update(**links[i['id']],implementation_status='IMPLEMENTED',execution_status='NOT_EXECUTED')
 i['limit']='Finite declared implementation only. Original physical/theoretical limitations remain; no scientific promotion from execution.'
mapping['implementation']='candidate-0.3';mapping['deferred']=['general R125 arbitrary cancellation/lease transport','bootstrap chemistry without seed','physical PW Hamiltonian','microscopic spin-hole-proton material','thermodynamic actuator/energy closure','origin of geometry and measure','general profile category and congruence']
mapping['full_design_claim']='16 executable finite comparisons; not all 12 blocks physically realized. Block boundaries must be reported.'
plan.update(implementation='candidate-0.3-full-comparison-draft',freeze_state='FROZEN_BEFORE_AUTHOR_EXECUTION',executed=False)
plan['phase_limits']['smoke']['cases']=[c['id'] for c in cases['cases']]
plan['phase_limits']['calibrate']['cases']+=['full_base','full_cycles_writer','full_transport_patch','full_branch','full_bell_x','full_finite_dark_32','full_bath_32']
plan['phase_limits']['calibrate']['cases']=list(dict.fromkeys(plan['phase_limits']['calibrate']['cases']))
plan['budget'].update(forecast_status='Old e8f3eb2 forecast not applicable to candidate-0.3',prediction_seconds=None)
plan['acceptance'].update(sigma_min=3**.5*.0001/.01,condition_number=100,reconstruction_status='Declared 3x2 outcome map for two orthogonal populations only; not complete quantum tomography',reconstruction_noise_per_outcome=.0001,reconstruction_error_allowance=.01)
plan['proposed_main_tasks']=None
plan['scope_evidence_required']=True
write('CASES',cases);write('PROTOCOL',plan);write('IMPLEMENTATION_MAP',mapping)
# Independent prospective promises, retaining all 125 original contracts unchanged.
promises=[]
for ancestor,design,artifact,prediction in [
 ('R070','X02','control::v1_support','Exact support equality in the declared V1 law.'),
 ('R071','X02','full_V2_V1','V2 permits functional writer access absent in the V1 branch; outcome may fail if the shared template is incompatible.'),
 ('R055','X10','control::readout_wave','Actual singular values determine whether the fixed reconstruction tolerance is met; no full-rank-only claim.'),
 ('R096','X12','control::full_cut','Equal complete cut yields equal continuation; no probability of origin inferred.'),
 ('R123','X14','control::moving_coordinate_order','Coordinate reorder preserves local traces on moving worldlines; changing physical speed is a separate comparison.'),
 ('R064','X07','full_repeat_writer','Two finite repairs may consume stock; no invariant viability set or unlimited closure is inferred.'),
 ('R122','X06','full_route_inheritance','Removing transmitted template impairs child function under the same imported local laws; geometry remains given.'),
 ('R121','X04','full_record_apparatus','Record and apparatus are separately necessary in this finite route; provenance identifies actual replacement products.'),
 ('R125','X15','control::branch_coordinate_order','Two children share one donor; reorder cannot duplicate stock or deliver it before the signal.'),
 ('R047','X13','control::selection','Conditional selection retains denominator; only K intervention changes executed dynamics.'),
 ('R108','X08','full_classical_joint','Same marginal preparations may have different joint continuation; classical witness is not quantum evidence.'),
 ('R040','X10','full_load_cycle_32','Explicit finite wave loading and waiting can differ from static protected control; continuum BIC requires separate limiting evidence.')]:
 promises.append(dict(ancestor=ancestor,design=design,evidence=artifact,prediction=prediction,result_status='NOT_EXECUTED',return_if_failed='Record the failed candidate prediction and surviving imported conditions; do not alter the ancestor result.'))
for promise in promises:
 if promise['evidence'] in ('full_V2_V1','full_route_inheritance','full_repeat_writer'):
  promise['numeric_prediction']=dict(lower=1,upper=1)
write('SCOPE_RETURN_CONTRACTS',dict(schema=1,frozen_before_author_execution=True,promises=promises,all_125_original_contracts='ANCESTOR_CONTRACTS.json'))
zero=read('IMPORTED_ZERO_ROW');zero['candidate_03_imports']={'typed_reaction_table':'given Z3 composition, not chemistry derived from payment','writer_reader_roles':'given operational laws; products tested by their operations','geometry':'given worldlines and local beacon reach, not generated spacetime','template':'root two-port template given; descendants receive physical packet','quantum_preparation':'given Bell/dephased 4D states and CP measurement instrument','thermodynamics':'credits/material only; no new energy/entropy equality','finite_scope':'bounded repairs, finite fragments, finite memory; not unlimited autopoiesis'};write('IMPORTED_ZERO_ROW',zero)
print(json.dumps(dict(cases=len(cases['cases']),contrasts=len(cases['contrasts']),controls=len(plan['design_controls']),executed=False)))
