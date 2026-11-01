"""Static RESET worker: calibration solves only known NESS and seeded random RHS."""
import gc,hashlib,json,signal,time,traceback
from pathlib import Path
import numpy as np
from e002_exp.model import maxabs
from e002e_exp.model import make_full
from e002e_exp.export import serial,write_manifest,conditional_values
from e002e_exp.runtime import runtime_gate,kernel_hash
from e002e_corr_exp.environment import environment
from e002e_corr_exp.core import physicality,marginals,sector_check,array_hash
from .core import Reset,analyze,matrix_hash
from .numerics import Solver
from .certificates import uniqueness,state_record
from .plan import PROTOCOL,workload,cases,preflight,implementation_hash,implementation_manifest,protocol_hash,storage_preflight

IO_SECONDS=0.


def snapshot():
    out=environment()
    status=Path('/proc/self/status').read_text().splitlines()
    for key,name in (('VmPeak:','process_peak_vm_bytes'),('VmHWM:','process_peak_rss_bytes')):
        rows=[line for line in status if line.startswith(key)]
        if len(rows)!=1:raise ValueError('Memory high-water measurement unavailable')
        out[name]=int(rows[0].split()[1])*1024
    return out


def save(path,value):
    global IO_SECONDS
    tick=time.perf_counter()
    Path(path).write_text(json.dumps(serial(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    IO_SECONDS+=time.perf_counter()-tick


def save_vector(folder,name,x):
    global IO_SECONDS
    tick=time.perf_counter()
    path=folder/(name+'.npz');np.savez_compressed(path,vector=x)
    IO_SECONDS+=time.perf_counter()-tick
    if path.stat().st_size>900000:raise ValueError('Published vector exceeds per-file size cap')
    return path.name


def random_rhs(space,seed):
    rng=np.random.default_rng(seed);rho=np.zeros((space.d,space.d),complex)
    for g in space.groups:
        z=rng.normal(size=(len(g),len(g)))+1j*rng.normal(size=(len(g),len(g)))
        rho[np.ix_(g,g)]=(z+z.conj().T)/2
    rho-=np.trace(rho)*np.eye(space.d)/space.d
    x=space.pack(rho);x/=np.linalg.norm(x)
    return x


def measure_raw(model,x):
    out={}
    for name,op in model['observables'].items():
        v=complex(model['space'].row(op)@x)
        if name.startswith('C_'):out[name]=dict(re=v.real,im=v.imag)
        else:
            if abs(v.imag)>1e-9:raise ArithmeticError('Complex observable')
            out[name]=float(v.real)
    return out


def solve_model(model,evidence,mode,report,counts):
    """Also exercised end-to-end on independent small-model fixtures."""
    name=model['case']['model'];space=model['space'];production=mode=='production'
    rows=[];branches={};states={};targets={};reset_maps={};response_vectors={};phases=[]
    seed=PROTOCOL['calibration_seeds'][name];rhs=random_rhs(space,seed)
    baseline_rhs=None if production else save_vector(report,name+'_random_rhs',rhs)
    for method in ('lu','gmres_ilu'):
        branch=dict(flux={});branches[method]=branch;states[method]={}
        baseline_solver=Solver(model['L'],space,method=method);counts['factorizations']+=1
        start=time.perf_counter();rho0,eq=baseline_solver.solve(trace=1.);counts['NESS']+=1
        physicality(space,rho0,1e-9);raw0=measure_raw(model,rho0)
        for key in ('F','J_h','source','h6','P_m6_N2','inventory'):
            if abs(raw0[key]-evidence['baseline']['raw'][key])>1e-8:raise ArithmeticError('Published baseline mismatch: '+key)
        tau=marginals(space.unpack(rho0),tuple(PROTOCOL['dimensions']) if space.d==216 else model['dimensions'])[1]
        reset=Reset(space,tau,tuple(PROTOCOL['dimensions']) if space.d==216 else model['dimensions'])
        targets[method]=tau;reset_maps[method]=reset
        branch.update(rho0_sha256=array_hash(rho0),tau_sha256=array_hash(tau),target=reset.target)
        save_vector(report,name+'_'+method+'_target',tau)
        for gamma in PROTOCOL['gammas']:
            tick=time.perf_counter()
            if gamma==0:solver=baseline_solver;x=rho0;equation=eq
            else:
                solver=Solver(model['L'],space,gamma,reset,method);counts['factorizations']+=1
                if production:x,equation=solver.solve(trace=1.);counts['NESS']+=1
            record=dict(model=name,method=method,gamma=gamma,reset=reset.certificate)
            if gamma==0 or production:
                key=str(gamma);states[method][key]=x;raw=measure_raw(model,x);branch['flux'][key]=raw['F']
                record.update(state_file=save_vector(report,f'{name}_{method}_g{gamma}',x),equation=equation,
                              physicality=physicality(space,x,1e-9),raw=raw,reset_action=reset.certify_action(x))
                diag_start=time.perf_counter()
                record['diagnostics']=state_record(model,x,reset,gamma)
                record['diagnostic_seconds']=time.perf_counter()-diag_start
            if production and gamma==0:
                q=reset.apply(rho0)-rho0
                X,response_eq=solver.solve(-q,trace=0.);counts['response']+=1
                xr=space.unpack(X)
                if maxabs(xr-xr.conj().T)>1e-9:raise ArithmeticError('Response is not Hermitian')
                branch['S']=float((space.row(model['observables']['F'])@X).real)
                branch['q_sha256']=array_hash(q);branch['X_sha256']=array_hash(X)
                branch['response_equation']=response_eq
                branch['response_file']=save_vector(report,name+'_'+method+'_X',X)
                branch['q_file']=save_vector(report,name+'_'+method+'_q',q)
                branch['response_sector']=sector_check(space,xr,xr,1e-10)
                response_vectors[method]=X
                record['response']=dict(branch)
            elif not production:
                random_x,random_eq=solver.solve(rhs,trace=0.);counts['random_rhs']+=1
                record.update(random_equation=random_eq,random_rhs_file=baseline_rhs,
                    random_solution_file=save_vector(report,f'{name}_{method}_g{gamma}_random',random_x),
                    random_rhs_seed=seed,physical_reset_rhs_solved=False)
            if method=='lu':record['condition']=solver.condition_estimate();counts['condition_estimates']+=1
            record['solver']=solver.metrics();record['elapsed_seconds']=time.perf_counter()-tick
            rows.append(record);phases.append(dict(model=name,method=method,gamma=gamma,**record['solver']['timing']))
            if gamma==0:del baseline_solver
            del solver;gc.collect()
        branch['branch_seconds']=time.perf_counter()-start
    if maxabs(targets['lu']-targets['gmres_ilu'])>1e-9:raise ArithmeticError('Independent targets differ')
    for key in states['lu']:
        if maxabs(states['lu'][key]-states['gmres_ilu'][key])>1e-9:raise ArithmeticError('NESS solver discrepancy')
    if production:
        if maxabs(response_vectors['lu']-response_vectors['gmres_ilu'])>1e-9:raise ArithmeticError('Response solver discrepancy')
        result=analyze(branches['lu'],branches['gmres_ilu'],evidence['corr']['result']['signed_area'],evidence['corr']['result']['area_uncertainty'])
        for row in rows:
            other=next(r for r in rows if r['gamma']==row['gamma'] and r['method']!=row['method'])
            error={k:3*abs(row['raw'][k]-other['raw'][k]) for k in row['raw'] if not k.startswith('C_')}
            row['primitive_uncertainty']=error;row['conditional']=conditional_values(row['raw'],error)
    else:
        result=dict(status='CALIBRATION_ONLY_NO_NEW_PHYSICAL_RESET_RHS')
        if name=='QS':
            extra=PROTOCOL['calibration_extra_factor_cases'][0]
            options={k:extra[k] for k in ('method','rtol','atol','ilu_drop_tol','ilu_fill_factor')}
            solver=Solver(model['L'],space,extra['gamma'],reset_maps['lu'],**options);counts['factorizations']+=1
            x,eq=solver.solve(rhs);counts['random_rhs']+=1
            rows.append(dict(model=name,method='gmres_ilu_tight',gamma=extra['gamma'],random_equation=eq,
                random_rhs_file=baseline_rhs,random_solution_file=save_vector(report,name+'_tight_random',x),
                physical_reset_rhs_solved=False,reset=reset_maps['lu'].certificate,solver=solver.metrics()))
            reference=next(r for r in rows if r['method']=='lu' and r['gamma']==extra['gamma'])
            with np.load(report/reference['random_solution_file'],allow_pickle=False) as a:comparison=maxabs(a['vector']-x)
            if comparison>1e-8:raise ArithmeticError('Calibration tight ILU comparison failed')
            rows[-1]['independent_random_solution_difference']=comparison
            del solver;gc.collect()
    return dict(model=name,case=model['case'],branches=branches,rows=rows,result=result,phases=phases,
                area_reference=evidence['corr']['result']['signed_area'],u_area=evidence['corr']['result']['area_uncertainty'])


def run(config,output):
    output=Path(output)
    if (output/'report').exists():raise FileExistsError('Refusing overwrite')
    report=output/'report';report.mkdir(parents=True);started=time.perf_counter()
    try:
        return _run(config,report,started)
    except Exception as e:
        save(report/'failure.json',dict(type=type(e).__name__,message=str(e),elapsed_seconds=time.perf_counter()-started,traceback=traceback.format_exc()))
        save(report/'status.json',dict(status='FAILED',scientific_acceptance=False))
        (report/'RESULT.md').write_text('Время: NOT_EVALUABLE. Аварийное завершение.\n\n'+str(e)+'\nЧастичные данные не приняты.\n')
        write_manifest(report);raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)


def _run(config,report,started):
    global IO_SECONDS
    IO_SECONDS=0.
    before=snapshot();save(report/'config.json',config);save(report/'environment_before.json',before)
    gate=preflight(config,before);gate['storage']=storage_preflight(report.parent)
    save(report/'preflight.json',{k:v for k,v in gate.items() if k!='evidence'})
    preflight_seconds=time.perf_counter()-started
    if config['mode']=='calibration':
        def alarm(*_):raise TimeoutError('Predeclared bounded calibration wall limit')
        signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,PROTOCOL['calibration_wall_limit_seconds'])
    counts=dict.fromkeys(workload(config['mode']),0);records=[];phases=[]
    for case in cases():
        tick=time.perf_counter();print('START',case['model'],config['mode'],flush=True)
        model=make_full(case);assembly=time.perf_counter()-tick
        cert_start=time.perf_counter();certificate=uniqueness(model);cert_time=time.perf_counter()-cert_start
        save(report/(case['model']+'_uniqueness_scope_v1.json'),certificate)
        rec=solve_model(model,gate['evidence'][case['id']],config['mode'],report,counts)
        save(report/(case['model']+'_case.json'),rec);records.append(rec)
        phases.append(dict(model=case['model'],assembly_seconds=assembly,certificate_seconds=cert_time,total_seconds=time.perf_counter()-tick))
        save(report/'progress.json',dict(counts=counts,phases=phases));print('DONE',case['model'],flush=True)
        del model;gc.collect()
    if counts!=workload(config['mode']):raise ArithmeticError('Workload mismatch')
    save(report/'protocol.json',PROTOCOL);save(report/'dependencies.json',implementation_manifest())
    save(report/'status.json',dict(status='COMPLETED_NOT_ACCEPTED',mode=config['mode']))
    entries=[dict(path=p.name,size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(report.glob('*.npz'))]
    save(report/'data_manifest.json',dict(full_files=entries,full_total_bytes=sum(e['size'] for e in entries),
         published_count=len(entries),selection='All solution, target and RHS arrays; no unpublished arrays',coverage=1.))
    metrics=dict(counts=counts,phases=phases,environment_after=snapshot(),
        preflight_seconds=preflight_seconds,io_seconds=IO_SECONDS,
        implementation_sha256=implementation_hash(),kernel_sha256=kernel_hash(),protocol_sha256=protocol_hash(),
        source_commit=config['source_commit'],mode=config['mode'],
        runtime_gate=runtime_gate(config['forecast'],time.perf_counter()-started,gate['counts'],counts,gate['environment']['comparable'],config['mode']=='production'))
    save(report/'metrics.json',metrics)
    from .reporting import render
    text=render(config,metrics,records)
    (report/'RESULT.md').write_text(text);(report/'README.md').write_text(text);write_manifest(report)
    from .verify import verify_report
    tick=time.perf_counter();verify_report(report,finalized=False);verification=time.perf_counter()-tick
    metrics.update(verification_seconds=verification,complete_body_seconds=time.perf_counter()-started,
                   timing_scope='Through first independent verification; final metadata and final immutable verification are covered by enclosing service duration')
    metrics['runtime_gate']=runtime_gate(config['forecast'],time.perf_counter()-started,gate['counts'],counts,gate['environment']['comparable'],config['mode']=='production')
    metrics['environment_after']=snapshot()
    save(report/'metrics.json',metrics);text=render(config,metrics,records)
    (report/'RESULT.md').write_text(text);(report/'README.md').write_text(text)
    if config['mode']=='calibration':
        from .budget import forecast
        save(report/'calibration.json',forecast(config,metrics,records,before))
    write_manifest(report)
    verify_report(report,finalized=True)
    print('FINAL_REPORT_VERIFIED_NO_SUBSEQUENT_REPORT_WRITES',flush=True)
    return metrics
