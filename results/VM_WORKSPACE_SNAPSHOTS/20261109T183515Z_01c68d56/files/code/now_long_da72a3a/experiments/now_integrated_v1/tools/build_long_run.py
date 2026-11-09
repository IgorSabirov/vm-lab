"""Expand existing NOW cases; preserves 210 original cases and the same dynamics."""
import copy,itertools,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nowexp.state import Config
from nowexp.runner import workload_inventory
def read(n):return json.loads((ROOT/'preregistration'/n).read_text())
def save(n,x):(ROOT/'preregistration'/n).write_text(json.dumps(x,ensure_ascii=False,separators=(",",":"))+'\n')
cases,plan,amendment=read('CASES.json'),read('PROTOCOL.json'),read('FOUR_CANDIDATE_AMENDMENT.json')
if any(c['id'].startswith('patch::long::') or c['id'].startswith('wavegrid::') for c in cases['cases']):
    raise ValueError('long grid already applied')
original=copy.deepcopy(cases['cases']);extra=[];comparisons=[];cal=[];traces=[];smoke=[]
families=['flat','ising_order','cdt_strip','add_quiet','add_growing']
def geometry(f):return {} if f=='flat' else {'geometry':{'fixture':f,'horizon':2048}}
for f,g,fuel,delay,damage in itertools.product(families,[3,5,8],[96,144,192,288,384],[0,16,64],['writer','contact']):
    prefix=f'patch::long::{f}::g{g}::f{fuel}::d{delay}::{damage}'
    names={}
    for mode in ['off','on','sham']:
        name=prefix+'::'+mode;names[mode]=name
        cfg=dict(separate_apparatus=True,inherited_routes=True,forced_content=None,donor_precursor=96,
                 task_probe=True,donor_fuel=fuel,restoration_mode=mode,task_damage=damage,max_events=12000,
                 generations=g,supply_delay=delay,**geometry(f))
        Config(**cfg).validate()
        extra.append(dict(id=name,config=cfg,sampling_mode='finite_enumeration',amendment='R127',
                          parent_case='patch::'+f+'::full_base',long_panel='resource_depth',cost_stratum=f'classical::{f}::g{g}'))
        if fuel==384 and delay==0 and damage=='contact' and mode=='on':cal.append(name);traces.append(name)
        if f in ('ising_order','cdt_strip') and g==8 and fuel==384 and delay==0 and damage=='contact' and mode=='on':smoke.append(name)
    for other in ['off','sham']:
        comparisons.append(dict(id=prefix+'::on-'+other,cases=[names['on'],names[other]],weights=[1,-1],
            metric='mean_task_success',phases=['main'],scientific_role='matched repair intervention within fixed carrier, depth, stock and delay'))
for f,modes,detune,wait in itertools.product(families,[16,32,64],[-.15,-.10,-.07,-.04,-.02,0.,.02,.04,.07,.10,.15],[16,32,48,64]):
    prefix=f'wavegrid::{f}::m{modes}::e{detune:g}::w{wait}';names={}
    for memory in ['finite_dark','finite_static']:
        name=prefix+'::'+memory;names[memory]=name
        cfg=dict(separate_apparatus=True,inherited_routes=True,forced_content=[1,1],donor_precursor=30,
                 memory=memory,bath_modes=modes,detuning=detune,read_wait=wait,max_events=12000,**geometry(f))
        Config(**cfg).validate()
        extra.append(dict(id=name,config=cfg,sampling_mode='finite_enumeration',amendment='R127',
                          parent_case='full_'+memory+'_32',long_panel='wave_carrier',cost_stratum=f'wave::{f}::m{modes}::{memory}'))
        if detune==.07 and wait==32:cal.append(name)
        if detune==.07 and wait==32 and modes==64:traces.append(name)
        if f in ('flat','ising_order') and detune==.07 and wait==32 and modes==64 and memory=='finite_static':smoke.append(name)
    comparisons.append(dict(id=prefix+'::dark-static',cases=[names['finite_dark'],names['finite_static']],weights=[1,-1],
        metric='final_function',phases=['main'],scientific_role='full loaded/read/transferred finite memory cycle, no continuum claim'))
cases['cases']+=extra;cases['contrasts']+=comparisons
plan['phase_limits']['smoke']['cases']+=smoke
plan['phase_limits']['calibrate']['cases']+=cal
plan['trace_case_ids']=[c['id'] for c in original]+traces
plan['compact_profile_case_prefixes']=['patch::long::','wavegrid::']
plan['long_run']={'user_instruction':'Launch 10+ minutes of machine time, 2026-11-08',
    'minimum_machine_seconds':600,'empty_repeats':False,'original_cases':210,'added_cases':len(extra),
    'resource_cases':1350,'wave_cases':1320,'calibration_cases':cal,'smoke_cases':smoke,
    'trace_policy':'All outcome rows retained. Full snapshots for originals and 25 fixed new representative cases; joint profiles reconstructible from rows.',
    'scope':'Same Engine, unchanged physical rules. Conditional carrier fixtures; no equilibrium ensemble, C3-D or metric-emergence claim.'}
plan['protocol_revision']='1.5-long-parameter-run'
plan['phase_limits']['main']['memory_limit_mib']=4096
plan['phase_limits']['main']['disk_limit_mib']=1024
plan['phase_limits']['main']['hard_wall_seconds']=3600
plan['execution_authorization'].update(decision='User directly ordered 10+ minute machine run; standing audit waiver and full runtime gate retained',limits_unchanged=True)
inventory=workload_inventory(plan,cases);plan['workload_inventory']=inventory;plan['proposed_main_tasks']=inventory['main']['tasks']
amendment['new_cases'] += [c['id'] for c in extra]
amendment['new_contrasts'] += [c['id'] for c in comparisons]
amendment['main_task_count']=inventory['main']['tasks']
amendment['long_run_revision']=plan['long_run']
for n,x in [('CASES.json',cases),('PROTOCOL.json',plan),('FOUR_CANDIDATE_AMENDMENT.json',amendment)]:save(n,x)
print(json.dumps({'cases':len(cases['cases']),'contrasts':len(cases['contrasts']),'inventory':inventory,'new_calibration':len(cal),'new_smoke':len(smoke)}))
