"""Bounded target-VM calibration, never a production/F2 launcher."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import resource
import shutil
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None

def solver_probe(config, report, metrics):
    import gc
    import numpy as np
    from e002e_exp.model import make_full, make_small
    from e002e_exp.numerics import Bordered, state_checks, values, refinement_check
    from e002e_exp.observations import static_response, frequency_response, propagate_qrt, compare_qrt
    from e002e_exp.export import serial, real_values, conditional_values
    from e002e_exp.plan import inventory
    from e002c_exp.diagnostics import node_blocks
    num = config['numerics']; cases = config['case_ids']
    lookup = {c['id']:c for c in inventory()['full_static'] if c['block'] != 'F2'}
    if len(cases) != len(set(cases)) or not set(cases) <= set(lookup):
        raise ValueError('Calibration must use explicit non-heldout baseline IDs')
    metrics['cases'] = []; metrics['phase_times'] = []
    Path('full').mkdir(exist_ok=False)
    def phase(name, fn):
        print('START '+name, flush=True); t=time.perf_counter(); value=fn()
        row=dict(name=name, seconds=time.perf_counter()-t,
                 max_rss_bytes=1024*resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        metrics['phase_times'].append(row)
        save(report/'progress.json', dict(last_phase=row, completed_cases=len(metrics['cases'])))
        print('DONE '+name+' '+str(row['seconds']), flush=True)
        return value
    for cid in cases:
        case=lookup[cid]
        model=phase(cid+'/build', lambda:make_full(case))
        s=model['space']; L=model['L']
        primary=phase(cid+'/LU_factor', lambda:Bordered(L,s,**num['solver']))
        x, check=phase(cid+'/LU_NESS', lambda:primary.solve(trace=1.))
        quality=phase(cid+'/LU_quality', lambda:state_checks(L,s,x,num['state_tolerance']))
        if not quality['pass']: raise ArithmeticError('LU state quality failed')
        independent=phase(cid+'/ILU_factor', lambda:Bordered(L,s,**num['refinement_solver']))
        xr, checkr=phase(cid+'/GMRES_NESS', lambda:independent.solve(trace=1.))
        qr=phase(cid+'/GMRES_quality', lambda:state_checks(L,s,xr,num['state_tolerance']))
        raw=real_values(values(model,x)); rawr=real_values(values(model,xr))
        agreement=refinement_check(x,xr,raw,rawr,num['refinement_limits'])
        if not qr['pass'] or not agreement['pass_gate']:raise ArithmeticError('Independent NESS check failed')
        errors={k:num['error_envelope']['absolute_floor']+num['error_envelope']['difference_multiplier']*abs(v-rawr[k]) for k,v in raw.items()}
        record=dict(id=cid,case=case,dimension=s.size,nnz=L.nnz,raw=raw,
            conditional=conditional_values(raw,errors),primitive_uncertainty=errors,
            quality=quality,refinement_quality=qr,solve_check=check,refinement_solve_check=checkr,
            agreement=agreement,operator_checks=model['checks'],responses=[])
        if max(abs(raw['J_h']-raw['F']),abs(raw['source']-raw['F']))>10*num['state_tolerance']:
            raise ArithmeticError('Stationary flux balance failed')
        record['condition']=phase(cid+'/condition',primary.condition_estimate)
        record['simultaneous_factor_storage_bytes']=primary.factor_storage_bytes+independent.factor_storage_bytes
        for target in config.get('static_targets',[]):
            if target not in case['tasks']:raise ValueError('Target outside declared baseline case')
            y,v,ch=phase(cid+'/static_'+target,lambda:static_response(model,x,target,primary))
            yr,vr,chr=phase(cid+'/static_ref_'+target,lambda:static_response(model,xr,target,independent))
            gate=refinement_check(y,yr,v,vr,num['refinement_limits'])
            if not gate['pass_gate']:raise ArithmeticError('Static refinement disagreement')
            record['responses'].append(dict(kind='static',target=target,values=v,check=ch,refinement=gate))
        record['primary_solver']=primary.metrics();record['independent_solver']=independent.metrics()
        del independent;gc.collect()
        for omega in config.get('frequencies',[]):
            y,v,ch,met=phase(cid+'/frequency_'+str(omega),lambda:frequency_response(model,x,omega,primary,**num['solver']))
            yr,vr,chr,metr=phase(cid+'/frequency_ref_'+str(omega),lambda:frequency_response(model,xr,omega,None,**num['refinement_solver']))
            gate=refinement_check(y,yr,v,vr,num['refinement_limits'])
            if not gate['pass_gate']:raise ArithmeticError('Frequency refinement disagreement')
            record['responses'].append(dict(kind='frequency',omega=omega,values=v,check=ch,refinement=gate,primary=met,independent=metr))
            record['simultaneous_factor_storage_bytes']=max(record['simultaneous_factor_storage_bytes'],primary.factor_storage_bytes+max(met['factor_storage_bytes'],metr['factor_storage_bytes']))
        np.savez_compressed(Path('full')/(cid+'_state.npz'),state=x,reference=xr)
        blocks=node_blocks(s.unpack(x))
        save(report/(cid+'_nodes.json'),dict(real=blocks.real.tolist(),imag=blocks.imag.tolist()))
        q=config.get('qrt_probe')
        if q:
            outputs=[]
            for dt in q['steps']:
                out=phase(cid+'/QRT_dt_'+str(dt),lambda:propagate_qrt(model,x,q['horizon'],dt,q['sample_interval']))
                outputs.append(out)
                np.savez_compressed(report/(cid+'_qrt_'+str(dt)+'.npz'),times=out['times'],C=out['C'])
            comparisons=[compare_qrt(outputs[i],outputs[i-1],q['absolute_tolerance'],q['relative_tolerance']) for i in range(1,len(outputs))]
            record['qrt']=dict(horizon=q['horizon'],steps=q['steps'],summaries=[o['summary'] for o in outputs],comparisons=comparisons)
            if any(not r['pass_gate'] for r in comparisons):raise ArithmeticError('QRT refinement failed')
        save(report/(cid+'.json'),serial(record));metrics['cases'].append(serial(record))
        del primary,model,x,xr;gc.collect()
    metrics['status']='CALIBRATION_COMPLETED_NOT_ACCEPTED'

def run(config):
    started = time.perf_counter()
    report = Path('report'); report.mkdir(exist_ok=False)
    metrics = {'run_id': config['run_id'], 'source_commit': config['source_commit'],
               'phase': config['calibration_phase'], 'production_started': False,
               'F2_started': False, 'forecast': config['forecast']}
    failure = None
    try:
        from e002e_exp.runtime import environment, kernel_hash
        import numpy as np
        from scipy.sparse.linalg import gmres
        env = environment()
        metrics.update(environment=env, kernel_sha256=kernel_hash(),
                       launcher_binding=config['source_commit_binding'],
                       source_root_matches=Path(os.environ['VM_SOURCE_DIR']).resolve() == ROOT)
        if not metrics['source_root_matches']:
            raise ValueError('Launcher source root mismatch')
        mismatches = [p for p, h in config.get('pinned_source_files', config.get('reviewed_scientific_files', {})).items()
                      if hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != h]
        metrics['pinned_source_file_mismatches'] = mismatches
        if mismatches:
            raise ValueError('Reviewed scientific source differs: '+str(mismatches))
        metrics['resources'] = dict(
            free_disk_bytes=shutil.disk_usage('.').free,
            cgroup_membership=read('/proc/self/cgroup'),
            proc_limits=read('/proc/self/limits'),
            address_space_rlimit=list(resource.getrlimit(resource.RLIMIT_AS)),
            data_rlimit=list(resource.getrlimit(resource.RLIMIT_DATA)))
        metrics['compatibility'] = dict(
            gmres_signature=str(inspect.signature(gmres)),
            gmres_accepts_rtol='rtol' in inspect.signature(gmres).parameters,
            numpy_has_trapezoid=hasattr(np, 'trapezoid'),
            blas_threadpools_observed=env['threadpools'] is not None)
        import io, contextlib, scipy
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf):
            np.show_config(); scipy.show_config()
        maps=read('/proc/self/maps') or ''
        library_paths=sorted({line.split()[-1] for line in maps.splitlines()
            if '/' in line and any(key in line.lower() for key in ('blas','lapack','libomp','libgomp','libmkl'))})
        metrics['blas_audit']=dict(build_config=buf.getvalue(),loaded_libraries=[
            dict(path=p,sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in library_paths],
            process_threads=len(list(Path('/proc/self/task').iterdir())))
        if config['calibration_phase'] == 'environment':
            metrics['status'] = 'ENVIRONMENT_MEASURED_NOT_NUMERICALLY_CALIBRATED'
        elif config['calibration_phase'] == 'solver':
            if not env['threadpools'] or any(p['num_threads'] != 1 for p in env['threadpools']):
                raise ValueError('Single BLAS thread not measured')
            if resource.getrlimit(resource.RLIMIT_AS)[0] != config['address_space_limit_bytes']:
                raise ValueError('Declared job address-space ceiling is not active')
            if int(env['memory_available'].split()[0])*1024 < config['address_space_limit_bytes']+1024**3:
                raise MemoryError('Host memory below declared ceiling plus 1 GiB reserve')
            solver_probe(config,report,metrics)
        else:
            raise ValueError('Undeclared calibration phase')
    except Exception as exc:
        failure = type(exc).__name__+': '+str(exc)
        metrics.update(status='FAILED', failure=failure, traceback=traceback.format_exc())
    elapsed = time.perf_counter()-started
    metrics['runtime'] = dict(actual_seconds=elapsed, status='NOT_EVALUABLE',
        reason='FIRST_TARGET_ENVIRONMENT_PROBE_UNCALIBRATED_ESTIMATE',
        deviation_seconds=elapsed-config['forecast']['expected_seconds'])
    save(report/'config.json', config)
    save(report/'metrics.json', metrics)
    full=[]
    if Path('full').exists():
        full=[dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in Path('full').glob('*')]
    save(report/'data_manifest.json', {'full_data': full, 'selection': 'All declared calibration cases and phase timings; full states remain on VM', 'omissions': ['full Liouville state vectors from GitHub; hashes retained'] if full else []})
    (report/'README.md').write_text('E002e bounded target VM calibration. No production or F2. Exact data: metrics.json.\n')
    (report/'RESULT.md').write_text('Время: ориентир '+str(config['forecast']['expected_seconds'])+
        ' с; факт '+str(elapsed)+' с; NOT_EVALUABLE — первый замер.\n\n'+
        'Статус: '+metrics['status']+'. Фаза: '+config['calibration_phase']+'. Производственный запуск закрыт.\n'+
        ('Ошибка: '+failure+'\n' if failure else 'Паспорт, совместимость библиотек и происхождение кода: metrics.json.\n'))
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    if failure:
        raise RuntimeError(failure)
