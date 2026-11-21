"""Frozen conditional X26 experiment v3: one quantum state across all events.

No parameter search, fitting of controls, automatic retuning, or silent row drops.
The thermal port is a selective weak-coupling postulate with scattering switched
off during loading. The coherent port is integrated with the ring present.
"""
from __future__ import annotations
import copy
import hashlib
import itertools
import json
import math
import time
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import expm_multiply
from .add_mapping import (load_verified_carrier, EXPECTED_CARRIER_BLOB,
    combinatorial_invariants, map_local_motifs_to_r040, advance_one_add_step,
    permute_vertex_motifs)
from .integrated import local_transition_activity
from .model import R040Parameters
from .bic import check_direct_bic
from .thermal_loading import bright_bohr_transition
from .transfer import check_moving_projector_transport, projector_from_dark_vector
from .runner import run_spectral

BIC = 'BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL'

def encode(obj):
    if isinstance(obj, np.ndarray):
        if np.iscomplexobj(obj):
            return {'__complex_array__': True, 'real': obj.real.tolist(), 'imag': obj.imag.tolist()}
        return obj.tolist()
    if isinstance(obj, (complex, np.complexfloating)):
        return {'__complex__': [float(obj.real), float(obj.imag)]}
    if isinstance(obj, np.generic): return obj.item()
    if isinstance(obj, dict): return {str(k): encode(v) for k,v in obj.items()}
    if isinstance(obj, (list, tuple)): return [encode(v) for v in obj]
    return obj

def decode(obj):
    if isinstance(obj, dict):
        if '__complex_array__' in obj: return np.array(obj['real'])+1j*np.array(obj['imag'])
        if '__complex__' in obj: return complex(*obj['__complex__'])
        return {k:decode(v) for k,v in obj.items()}
    if isinstance(obj,list): return [decode(v) for v in obj]
    return obj

def canonical(obj): return json.dumps(encode(obj), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(obj): return hashlib.sha256(canonical(obj)).hexdigest()
def dump(path, obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(encode(obj), indent=2, ensure_ascii=False, allow_nan=False)+'\n'
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(text); tmp.replace(path)
    json.loads(path.read_text())

def prepare_cases(m):
    c=load_verified_carrier(Path(__file__).resolve().parents[1]/m['carrier']['path'])
    cases=[]
    for cfg in m['cases']:
        word=list(cfg['word']); anchors=dict(m['carrier']['anchors'])
        inv=combinatorial_invariants(word)
        maps=[]; steps=[]
        for i in range(3):
            maps.append(map_local_motifs_to_r040(word,anchors,m['phi']))
            if i<2:
                step=advance_one_add_step(word,anchors,c.full_step)
                steps.append(step); word=step['word_after']; anchors=step['anchors_after']
        act=local_transition_activity(steps[0]['word_before'],steps[0]['anchors_before'],
            steps[0]['word_after'],steps[0]['anchors_after'],m['phi']['radius'],m['psi']['activity_scale'])
        ps=[R040Parameters(**x['parameters']) for x in maps]
        cases.append({'id':cfg['id'], 'invariants':inv,'phi':maps,'steps':steps,
                      'activity':act,'parameters':ps,'bic':[check_direct_bic(p) for p in ps],
                      'anchor_collisions':[len(set(s['anchors_after'].values()))<3 for s in steps]})
    return cases

def tasks(m):
    result=[]
    for case,route,control,n,res in itertools.product(
        [x['id'] for x in m['cases']],m['routes'],m['controls'],m['ring_sizes'],range(len(m['accuracy']))):
        result.append(dict(kind='cycle',case=case,route=route,control=control,N=n,res=res))
    for case,snapshot in itertools.product([x['id'] for x in m['cases']],range(3)):
        result.append(dict(kind='spectral',case=case,snapshot=snapshot))
    for family,duration,n,res in itertools.product(m['ramp']['families'],m['ramp']['durations'],m['ring_sizes'],range(len(m['accuracy']))):
        result.append(dict(kind='ramp',family=family,duration=duration,N=n,res=res))
    for i,t in enumerate(result): t['id']=f't{i:04d}'; t['stratum']=stratum(t)
    return result

def stratum(t):
    if t['kind']=='cycle': return f"cycle/{t['case']}/{t['route']}/{t['control']}/N{t['N']}/r{t['res']}"
    if t['kind']=='ramp': return f"ramp/{t['family']}/T{t['duration']}/N{t['N']}/r{t['res']}"
    return f"spectral/{t['case']}/s{t['snapshot']}"

def workload(m):
    ts=tasks(m)
    return {'schema':3,'manifest_digest':digest(m),'task_digest':digest(ts),'total':len(ts),
            'counts':{k:sum(t['kind']==k for t in ts) for k in ['cycle','spectral','ramp']},
            'max_H_dimension':3+max(m['ring_sizes']), 'tasks':ts,
            'adaptive_steps':'measured, not assumed', 'resume':'same manifest/code only, completed task hashes verified'}

def preflight(m):
    errors=[]
    def need(ok,msg):
        if not ok: errors.append(msg)
    try:
        need(m['schema']==3 and m['freeze_state']=='FROZEN','schema/freeze')
        need(m['epistemic_class']=='CONDITIONAL_MODEL_NOT_ADD_DERIVED','epistemic class')
        need(bool(m['authorization']['instruction']),'authorization')
        canonical(m)  # rejects all NaN/Inf
        def no_null(v):
            if v is None: raise ValueError('null physical field')
            if isinstance(v,dict):
                for x in v.values(): no_null(x)
            if isinstance(v,list):
                for x in v: no_null(x)
        no_null(m)
        need(m['carrier']['expected_git_blob_sha1']==EXPECTED_CARRIER_BLOB,'carrier digest')
        need(m['carrier']['semantics']=='FIG2A_FULL_CONDITIONAL_U009_OPEN','carrier semantics')
        need(m['carrier']['merge_law']=='THREE_DISTINCT_INTERNAL_ROLE_MODES','merge law')
        need(m['transport']=='IDENTITY_ON_ROLE_AND_BATH_BASIS','quantum transport')
        need(m['units']=={'hbar':1.0,'k_B':1.0,'energy':'kappa','time':'hbar/kappa'},'units')
        need(m['routes']==['coherent','thermal'],'routes')
        need(m['controls']==['active','loader_off','trigger_off','bad_transport','no_resource'],'controls')
        need(len(m['ring_sizes'])>=3 and all(type(n) is int and n>=16 for n in m['ring_sizes'])
             and m['ring_sizes']==sorted(set(m['ring_sizes'])),'ring sizes')
        need(len(m['accuracy'])==2,'refinement pair')
        for a in m['accuracy']:
            need(all(0<float(a[k])<=.25 for k in ['rtol','atol','max_step']),'finite positive solver tolerances')
        for k in ['duration','hold_duration','activity_scale','omega','beta','gamma_down','latency']:
            need(float(m['psi'][k])>0,'psi '+k)
        need(m['psi']['thermal_contact']=='OFF_DURING_LOADING_ON_FOR_HOLD','thermal contact')
        need(m['psi']['initial_state']=='UPPER_BRIGHT_EIGENVECTOR_OF_H1','initial state')
        need(m['ramp']['families']==['g_only','moving_dark'],'ramp families')
        need(all(float(t)>0 for t in m['ramp']['durations']),'ramp durations')
        for k,v in m['resources'].items():
            if isinstance(v,(float,int)): need(v>=0,'resource '+k)
        need(0<m['resources']['efficiency']<=1,'efficiency')
        need(m['resources']['reset_work_per_bit']>=m['resources']['controller_temperature']*math.log(2),'reset below Landauer')
        need(m['resources']['fuel']>0 and m['resources']['precursors']>=1,'resource stock')
        need(m['resources']['reservoir']=='IDEAL_ISOTHERMAL_EXTERNAL_LOADING_RESERVOIR','reservoir')
        cs=prepare_cases(m)
        need(len({c['id'] for c in cs})==len(cs),'duplicate cases')
        for c in cs: need(c['invariants']['E0'],'initial case outside E0: '+c['id'])
        original=next(x for x in m['cases'] if x['id']=='active_word')['word']
        permuted=next(x for x in m['cases'] if x['id']=='permuted_word')['word']
        need(permute_vertex_motifs(original,m['permutation'])==permuted,'permutation mismatch')
        need(combinatorial_invariants(original)['pure_half_counts']==combinatorial_invariants(permuted)['pure_half_counts'],'half counts changed')
        need(m['spectral']['numerics']['pole_residual_tolerance']>0,'spectral tolerance')
        # All spectral inputs are bound to this manifest and derived Phi, never an old receipt.
        for k in ['continuum_scan','pole_search','diagnostics','numerics','loading']: need(k in m['spectral'],'spectral '+k)
        need(m['limits']['hard_wall_seconds']>0 and m['limits']['memory_mib']>=512,'execution limits')
        workload(m)
    except (KeyError,TypeError,ValueError,ArithmeticError,OSError) as e:
        errors.append(type(e).__name__+': '+str(e))
    return {'status':'INPUT_PASS' if not errors else 'STOP_INPUT','submit_allowed':not errors,
            'blockers':errors,'runtime_gate':'SEPARATE_TARGET_VM_CALIBRATION_REQUIRED'}

def hamiltonian(p,n,g=None):
    h=np.zeros((n+3,n+3),complex);h[:3,:3]=p.H3
    for i in range(n):
        h[3+i,3+i]=p.bath_onsite
        j=(i+1)%n;h[3+i,3+j]=h[3+j,3+i]=p.kappa
    h[2,3]=h[3,2]=p.g if g is None else g
    return h

def extend(v,n):
    x=np.zeros(n+3,complex);x[:3]=v;return x

def density(columns): return columns@columns.conj().T
def energy(h,c): return float(np.sum(c.conj()*(h@c)).real)
def pop(d,c): return float(np.sum(np.abs(d.conj()@c)**2))
def entropy(c):
    vals=np.linalg.eigvalsh(c.conj().T@c).real;vals=vals[vals>1e-14]
    return float(-sum(vals*np.log(vals)))

def reserve_cost(m,p0,p1,route,active,bad=False):
    r=m['resources']; ctrl=2*m['psi']['omega'] if route=='coherent' and active else 0.
    # A priori norm bounds for noncommuting quantum kick and Hamiltonian quench.
    quench=2*(np.linalg.norm(p0.H3,2)+np.linalg.norm(p1.H3,2)+p0.g+p1.g)
    bits=r['memory_bits'];fixed=r['packet_cost']+r['readout_cost']+bits*r['reset_work_per_bit']
    switching=r['switch_cost']*(2 if route=='thermal' and active else 1)
    thermal_gate=r['thermal_gate_cost'] if route=='thermal' and active else 0.
    return {'reserved_fuel':float((ctrl+quench)/r['efficiency']+fixed+switching+thermal_gate),
            'fixed_cost':fixed+switching+thermal_gate,'work_upper_bound':float(ctrl+quench),
            'heat_upper_bound':float(2*np.linalg.norm(p0.H3,2))}

def cycle(m,case,t,out):
    n=t['N'];a=m['accuracy'][t['res']]; cfg=m['psi']; control=t['control']; route=t['route']
    p1,p2=case['parameters'][1:]; d1=extend(p1.dark_vector,n);d2=extend(p2.dark_vector,n)
    base={'task':t,'technical_pass':True,'case_E0':case['invariants']['E0'],
          'K':case['invariants']['K'],'bic_before':case['bic'][1]['verdict'],
          'bic_after':case['bic'][2]['verdict'],'activity_score':case['activity']['activity_score'],
          'chronology':['observe_X0_to_X1','latency_and_packet_preparation','load_on_H1',
                        'close_loader_restore_contact','X1_to_X2_and_T','hold_on_H2','readout_reset']}
    if case['bic'][1]['verdict']!=BIC:
        return {**base,'physical_status':'NOT_EVALUABLE_NO_INITIAL_BIC','evolution_executed':False}
    b3=np.array(bright_bohr_transition(p1)['bright_vector']);b=extend(b3,n)
    activity=case['activity']['activity_score'] if control!='trigger_off' else 0.
    enabled=control not in ('loader_off','no_resource') and activity>0
    reservation=reserve_cost(m,p1,p2,route,enabled,control=='bad_transport')
    available=0. if control=='no_resource' else m['resources']['fuel']
    if reservation['reserved_fuel']>available or m['resources']['precursors']<int(enabled):
        return {**base,'physical_status':'RESOURCE_BLOCKED_BEFORE_PREPARATION','evolution_executed':False,
                'resource':{'available':available,**reservation,'consumed':0.}}
    h1=hamiltonian(p1,n); h2=hamiltonian(p2,n)
    ts=np.linspace(0,cfg['duration'],m['samples']); wp=wm=q=0.;initial_energy=energy(h1,b[:,None]);nfev=0
    loading_vectors=[];load_pop=[];load_bath=[];load_energy=[];load_trace=[]
    def env(tau): return math.sin(math.pi*tau/cfg['duration'])**2
    def denv(tau): return math.pi/cfg['duration']*math.sin(2*math.pi*tau/cfg['duration'])
    if route=='coherent':
        c3=cfg['omega']*activity*(np.outer(p1.dark_vector,p1.bright_vector.conj())+np.outer(p1.bright_vector,p1.dark_vector.conj()))
        if not enabled: c3*=0
        hc=np.zeros_like(h1);hc[:3,:3]=c3;hs=csr_matrix(h1);cs=csr_matrix(hc)
        def rhs(tau,y):
            ket=y[:-2];power=float(np.vdot(ket,cs@ket).real)*denv(tau)
            return np.r_[-1j*(hs@ket+env(tau)*(cs@ket)),max(0.,power),max(0.,-power)]
        sol=solve_ivp(rhs,(0,ts[-1]),np.r_[b,0j,0j],t_eval=ts,method='DOP853',**a)
        if not sol.success: raise RuntimeError(sol.message)
        nfev=sol.nfev;wp=float(sol.y[-2,-1].real);wm=float(sol.y[-1,-1].real)
        for i,tau in enumerate(ts):
            c=sol.y[:-2,i,None];loading_vectors.append(c)
            load_pop.append(pop(d1,c));load_bath.append(float(np.sum(abs(c[3:])**2)))
            load_energy.append(energy(h1+env(tau)*hc,c));load_trace.append(float(np.sum(abs(c)**2)))
        loaded=loading_vectors[-1];minimum_eigen=0.;sload=0.;q=0.;bohr={}
    else:
        # Contact absent throughout selective thermal loading; exact H3 Bohr pair.
        trans=bright_bohr_transition(p1);gap=trans['bohr_gap'];d=p1.dark_vector
        pd=np.outer(d,d.conj());pb=np.outer(b3,b3.conj());ld=np.outer(d,b3.conj());lu=ld.conj().T
        rate=cfg['gamma_down']*activity if enabled else 0.;up=rate*math.exp(-cfg['beta']*gap)
        def rhs(tau,y):
            rho=y[:9].reshape(3,3); f=env(tau)
            diss=rate*(ld@rho@lu-.5*(pb@rho+rho@pb))+up*(lu@rho@ld-.5*(pd@rho+rho@pd))
            dr=-1j*(p1.H3@rho-rho@p1.H3)+f*diss
            heat=gap*f*(rate*np.trace(pb@rho).real-up*np.trace(pd@rho).real)
            return np.r_[dr.ravel(),heat]
        sol=solve_ivp(rhs,(0,ts[-1]),np.r_[np.outer(b3,b3.conj()).ravel(),0j],t_eval=ts,method='DOP853',**a)
        if not sol.success: raise RuntimeError(sol.message)
        nfev=sol.nfev; q=float(sol.y[-1,-1].real);minimum_eigen=1.
        for i in range(len(ts)):
            rho=sol.y[:9,i].reshape(3,3);rho=(rho+rho.conj().T)/2
            vals,vecs=np.linalg.eigh(rho);minimum_eigen=min(minimum_eigen,float(min(vals)))
            load_pop.append(float(np.trace(pd@rho).real));load_bath.append(0.)
            load_energy.append(float(np.trace(p1.H3@rho).real));load_trace.append(float(np.trace(rho).real))
        vals,vecs=np.linalg.eigh(rho)
        # Negative roundoff recorded before clipping; tolerance gate below rejects material negativity.
        loaded=np.zeros((n+3,3),complex);loaded[:3]=vecs*np.sqrt(np.maximum(vals,0))
        sload=entropy(loaded);bohr={'gap':gap,'rate_down':rate,'rate_up':up,'contact_off':True,
                                   'global_unique_steady_state':False}
    rload=density(loaded)
    # Both contact quenches have zero expected contact energy for the declared
    # factorized thermal packet. Compute restoration rather than assume zero.
    contact_work=energy(h1,loaded)-load_energy[-1]
    tx=np.eye(n+3,dtype=complex)
    if control=='bad_transport': tx[[0,2]]=tx[[2,0]]
    transferred=tx@loaded
    quench_work=energy(h2,transferred)-energy(h1,loaded)
    transport=check_moving_projector_transport(projector_from_dark_vector(d1),projector_from_dark_vector(d2),tx)
    hold_ts=np.linspace(0,cfg['hold_duration'],m['samples'])
    hold=expm_multiply(-1j*csr_matrix(h2),transferred,start=0,stop=hold_ts[-1],num=len(hold_ts),endpoint=True,traceA=-1j*np.trace(h2))
    hold_p=[pop(d2,c) for c in hold];hold_e=[energy(h2,c) for c in hold]
    hold_bath=[float(np.sum(abs(c[3:])**2)) for c in hold]
    final=hold[-1];ef=energy(h2,final)
    balance=ef-initial_energy-(wp-wm)-contact_work-quench_work+q
    consumed=reservation['fixed_cost']+(wp+max(0.,contact_work)+max(0.,quench_work))/m['resources']['efficiency']
    trace_err=max(max(abs(np.array(load_trace)-1)),max(abs(float(np.sum(abs(c)**2))-1) for c in hold))
    checks={'trace_error':float(trace_err),'density_min_eigenvalue_before_roundoff_clipping':minimum_eigen,
            'energy_balance_residual':float(balance),'hold_energy_drift':float(max(abs(np.array(hold_e)-hold_e[0]))),
            'budget_bound_respected':bool(consumed<=reservation['reserved_fuel']+m['thresholds']['energy']),
            'thermal_entropy_production':sload+cfg['beta']*q if route=='thermal' else 0.}
    checks['closed_loader_null_pass']=(max(load_pop+hold_p)<=m['thresholds']['null_leak']) if control in ('loader_off','trigger_off') and case['bic'][2]['verdict']==BIC else True
    checks['bad_transport_detected']=(not transport['projector_intertwining_pass']) if control=='bad_transport' else True
    technical=(trace_err<=m['thresholds']['trace'] and minimum_eigen>=-m['thresholds']['positivity']
        and abs(balance)<=m['thresholds']['energy'] and checks['hold_energy_drift']<=m['thresholds']['energy']
        and checks['budget_bound_respected'] and checks['thermal_entropy_production']>=-m['thresholds']['energy']
        and checks['closed_loader_null_pass'] and checks['bad_transport_detected'])
    frozen_target=(case['bic'][2]['verdict']==BIC)
    good=(load_pop[-1]>=m['thresholds']['loaded_population'] and frozen_target
          and min(hold_p)>=m['thresholds']['retained_fraction']*load_pop[-1]
          and transport['isometry_pass'] and transport['projector_intertwining_pass'])
    artifact=out/(t['id']+'_states.npz')
    np.savez_compressed(artifact,rho_load=rload,rho_after=density(transferred),rho_final=density(final),
                        H_before=h1,H_after=h2,T=tx,P_before=np.outer(d1,d1.conj()),P_after=np.outer(d2,d2.conj()))
    return {**base,'evolution_executed':True,'technical_pass':bool(technical),
        'physical_status':'CRITERION_MET_CONDITIONAL_MODEL' if good else 'CRITERION_NOT_MET',
        'loading':{'times':ts.tolist(),'target_population':load_pop,'bath_population':load_bath,
                   'energy':load_energy,'trace':load_trace,'bohr':bohr,'nfev':nfev},
        'hold':{'times':hold_ts.tolist(),'target_population':hold_p,'bath_population':hold_bath,'energy':hold_e},
        'transfer':transport,'p_load':load_pop[-1],'p_after':hold_p[0],'p_final':hold_p[-1],
        'p_bath_final':hold_bath[-1], 'P_leak_final':1-hold_p[-1], 'energy_initial':initial_energy,'energy_final':ef,
        'work':{'control_input':wp,'control_return':wm,'contact_restore':contact_work,
                'carrier_and_T_quench':quench_work,'loading_reservoir_heat_gained':q},
        'resource':{**reservation,'available':available,'consumed':consumed,'remaining':available-consumed,
            'precursors_consumed':int(enabled),'reset_work':m['resources']['memory_bits']*m['resources']['reset_work_per_bit'],
            'reset_Landauer_lower_bound':m['resources']['memory_bits']*m['resources']['controller_temperature']*math.log(2),
            'status':'CONDITIONAL_COST_CONTRACT_ONLY_EXTERNAL_RESOURCES_NOT_REPRODUCED'},
        'checks':checks,'states_file':artifact.name,'states_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}

def ramp(m,t,out):
    n=t['N'];duration=t['duration'];a=m['accuracy'][t['res']];cfg=m['ramp']
    def par(u):
        s=3*u*u-2*u*u*u
        r=1+(cfg['ratio_end']-1)*s if t['family']=='moving_dark' else 1.
        g=cfg['g_start']+(cfg['g_end']-cfg['g_start'])*s if t['family']=='g_only' else cfg['g_start']
        return R040Parameters(E_V=.3+.25*(r-1/r),E_1=.3,E_2=.25,t_1=.25,t_2=.3,gamma_d=.3*r,kappa=1.,g=g)
    p0=par(0);d0=extend(p0.dark_vector,n);base=csr_matrix(hamiltonian(p0,n))
    def rhs(tau,ket):
        p=par(tau/duration);v=base@ket;v[:3]+=(p.H3-p0.H3)@ket[:3]
        dg=p.g-p0.g;v[2]+=dg*ket[3];v[3]+=dg*ket[2]
        return -1j*v
    ts=np.linspace(0,duration,m['samples'])
    sol=solve_ivp(rhs,(0,duration),d0,t_eval=ts,method='DOP853',**a)
    if not sol.success: raise RuntimeError(sol.message)
    leak=[];bath=[];target_res=[]
    for i,tau in enumerate(ts):
        p=par(tau/duration);d=extend(p.dark_vector,n);v=sol.y[:,i]
        leak.append(float(1-abs(np.vdot(d,v))**2));bath.append(float(sum(abs(v[3:])**2)))
        target_res.append(float(np.linalg.norm(p.H3@p.dark_vector-p.dark_energy*p.dark_vector)))
    norm=float(max(abs(np.sum(abs(sol.y)**2,axis=0)-1)))
    technical=norm<=m['thresholds']['trace'] and max(target_res)<=m['thresholds']['trace']
    if t['family']=='g_only': technical=technical and max(abs(np.array(leak)))<=m['thresholds']['null_leak']
    delta=cfg['g_end']-cfg['g_start'] if t['family']=='g_only' else cfg['ratio_end']-1
    artifact=out/(t['id']+'_states.npz')
    np.savez_compressed(artifact,times=ts,ket=sol.y)
    return {'task':t,'technical_pass':bool(technical),'physical_status':'DIAGNOSTIC_ONLY',
            'speed':abs(delta)/duration,'times':ts.tolist(),'leakage':leak,'bath_population':bath,
            'leakage_final':leak[-1],'bath_final':bath[-1],'norm_error':norm,'nfev':sol.nfev,
            'target_eigen_residual':max(target_res),'fit_claim':'no universal slope imposed',
            'states_file':artifact.name,'states_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}

def execute(m,cases,t,out):
    if t['kind']=='cycle': return cycle(m,next(c for c in cases if c['id']==t['case']),t,out)
    if t['kind']=='ramp': return ramp(m,t,out)
    case=next(c for c in cases if c['id']==t['case']);cfg=copy.deepcopy(m['spectral'])
    cfg['model']=case['phi'][t['snapshot']]['parameters'];report=run_spectral(cfg)
    return {'task':t,'technical_pass':report['technical_checks']['overall_technical_pass'],
            'physical_status':'SPECTRAL_CLASSIFIED','report':report,'derived_manifest_digest':digest(cfg)}

def aggregate(m,rows):
    cycle_rows=[r for r in rows if r['task']['kind']=='cycle']
    comparisons=[]
    for case,route in itertools.product([x['id'] for x in m['cases']],m['routes']):
        selected={r['task']['control']:r for r in cycle_rows if r['task']['case']==case and r['task']['route']==route
                  and r['task']['N']==max(m['ring_sizes']) and r['task']['res']==1}
        active=selected['active'];baseline=[selected[k] for k in ['loader_off','trigger_off']]
        evaluable=all(r.get('evolution_executed') for r in [active,*baseline])
        contrast=min(active['p_final']-r['p_final'] for r in baseline) if evaluable else None
        comparisons.append({'case':case,'route':route,'evaluable':evaluable,'minimum_p_final_contrast':contrast,
          'physical_status':('CRITERION_MET' if active['physical_status']=='CRITERION_MET_CONDITIONAL_MODEL'
            and contrast>=m['thresholds']['contrast'] else 'CRITERION_NOT_MET') if evaluable else active['physical_status']})
    convergence=[]
    groups={}
    for r in cycle_rows:
        if r.get('evolution_executed'):
            t=r['task'];groups.setdefault((t['case'],t['route'],t['control']),[]).append(r)
    for key,rs in groups.items():
        get=lambda n,q:next(r for r in rs if r['task']['N']==n and r['task']['res']==q)
        n1,n2=m['ring_sizes'][-2:]
        dn=max(abs(get(n1,1)[k]-get(n2,1)[k]) for k in ['p_load','p_after','p_final','p_bath_final'])
        dt=max(abs(get(n2,0)[k]-get(n2,1)[k]) for k in ['p_load','p_after','p_final','p_bath_final'])
        convergence.append({'group':list(key),'N_error':dn,'accuracy_error':dt,
                             'pass':dn<=m['thresholds']['N_convergence'] and dt<=m['thresholds']['refinement']})
    ramps=[]
    for family in m['ramp']['families']:
        rr=[r for r in rows if r['task']['kind']=='ramp' and r['task']['family']==family]
        for n in m['ring_sizes']:
            refined=[r for r in rr if r['task']['N']==n and r['task']['res']==1]
            usable=[r for r in refined if r['leakage_final']>m['thresholds']['fit_floor']]
            fit={'status':'NOT_EVALUABLE_BELOW_FLOOR_OR_TOO_FEW_POINTS','slope':None}
            if len(usable)>=3:
                x=np.log([r['speed'] for r in usable]);y=np.log([r['leakage_final'] for r in usable])
                slope,intercept=np.polyfit(x,y,1);pred=intercept+slope*x
                r2=1-float(sum((y-pred)**2)/sum((y-y.mean())**2)) if np.ptp(y)>1e-14 else None
                fit={'status':'DESCRIPTIVE_FINITE_RANGE_FIT','slope':float(slope),'R_squared':r2,
                     'power_law_diagnostic_pass':r2 is not None and r2>=m['thresholds']['fit_R2'],
                     'universal_law_claim':False}
            ramps.append({'family':family,'N':n,'fit':fit})
    ramp_convergence=[]
    for family,duration in itertools.product(m['ramp']['families'],m['ramp']['durations']):
        get=lambda n,q:next(r for r in rows if r['task']['kind']=='ramp' and r['task']['family']==family
            and r['task']['duration']==duration and r['task']['N']==n and r['task']['res']==q)
        n1,n2=m['ring_sizes'][-2:]
        dn=max(abs(get(n1,1)[k]-get(n2,1)[k]) for k in ['leakage_final','bath_final'])
        dt=max(abs(get(n2,0)[k]-get(n2,1)[k]) for k in ['leakage_final','bath_final'])
        ramp_convergence.append({'family':family,'duration':duration,'N_error':dn,'accuracy_error':dt,
                                 'pass':dn<=m['thresholds']['N_convergence'] and dt<=m['thresholds']['refinement']})
    return {'task_count':len(rows),'planned':len(tasks(m)),
        'technical_pass':all(r['technical_pass'] for r in rows) and all(x['pass'] for x in convergence+ramp_convergence),
        'outcome_counts':{s:sum(r['physical_status']==s for r in rows) for s in sorted({r['physical_status'] for r in rows})},
        'causal_comparisons':comparisons,'cycle_convergence':convergence,'ramp_convergence':ramp_convergence,'ramp_fits':ramps,
        'scientific_status':'CONDITIONAL_FINITE_PROTOCOL_ONLY_NO_ADD_DERIVATION_NO_NOW_PROMOTION'}
