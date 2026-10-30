"""E002d: full-CSR evolution, independent interventions and GitHub report."""
import hashlib,json,os,platform,shutil,sys,time,traceback
from pathlib import Path
import numpy as np
import scipy
from e002_exp.model import save_json
from e002c_exp.engine import Trajectory,stationarity
from e002c_exp.export import export_case,extrema,digest,array_spec
from .model import build,consequence_map
from .plan import cases,counts,CALIBRATION_FORECAST
from .analysis import analyze
from e002c_exp.windows import integral_mean

ROOT=Path(__file__).resolve().parents[1]

def kernel_files():
    return [ROOT/'e002_exp/model.py',*[ROOT/'e002c_exp'/f for f in
        ('model.py','engine.py','diagnostics.py','windows.py','export.py')],
        *sorted((ROOT/'e002d_exp').glob('*.py')),ROOT/'run.py']

def kernel_hash():
    h=hashlib.sha256()
    for p in kernel_files():h.update(p.relative_to(ROOT).as_posix().encode()+b'\0'+p.read_bytes())
    return h.hexdigest()

def preflight(config):
    mode=config['mode'];cs=cases(mode)
    if len({c['id'] for c in cs})!=len(cs):raise ValueError('Duplicate cases')
    if mode=='production':
        if counts(mode)!=dict(trajectories=36,steps=1160000,rhs_calls=4640000):raise ValueError('Wrong production volume')
        cal=config['calibration']
        if cal['kernel_sha256']!=kernel_hash():raise ValueError('Kernel changed since calibration')
        if cal['numpy']!=np.__version__ or cal['scipy']!=scipy.__version__:raise ValueError('Library version changed')
        if cal.get('review_status')!='VERIFIED_GITHUB':raise ValueError('Unverified calibration')
        if len(cal['report_commit'])!=40 or len(cal['source_commit'])!=40:raise ValueError('Calibration not pinned')
        if config['forecast']['relative_band']!=.4:raise ValueError('Invalid frozen band')
    elif mode=='calibration':
        if counts(mode)!=dict(trajectories=12,steps=9000,rhs_calls=36000):raise ValueError('Wrong calibration volume')
        if config['forecast']!=CALIBRATION_FORECAST:raise ValueError('Calibration forecast changed')
    if os.environ.get('VM_SOURCE_DIR') and Path(os.environ['VM_SOURCE_DIR']).name!=config['run_id']:
        raise ValueError('Run identity differs from VM source directory')
    if mode!='smoke' and shutil.disk_usage('.').free<3*1024**3:raise ValueError('Need 3 GiB free disk')
    return cs

def write_manifest(report,full):
    records=[];original=[]
    for root,out in ((report,records),(full,original)):
        for p in sorted(root.rglob('*')):
            if not p.is_file() or p.name=='data_manifest.json':continue
            item=dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=digest(p))
            if root==report and p.suffix=='.npz':item['arrays']=array_spec(p)
            out.append(item)
    save_json(report/'data_manifest.json',dict(exported=records,full=original,
        full_bytes=sum(r['bytes'] for r in original),
        selection='scalar .2 through 10 then 2; diagnostics 2 through 20 then 4; exact six-point reference windows separately',
        limitations=['Full-state positivity and node-edge PT depend on full VM states; reduced blocks cannot reconstruct them.',
          'Extrema before subsampling; full scalar/diagnostic series remain on VM.',
          'Calibration windows contain short diagnostic grids, not steady-state data.']))
    fs=[p for p in report.rglob('*') if p.is_file()]
    if len(fs)>500 or sum(p.stat().st_size for p in fs)>30*1024**2 or any(p.stat().st_size>8*1024**2 for p in fs):
        raise ValueError('Export budget exceeded')

def compact(metrics,checks):
    rt=checks['runtime_gate'];work=metrics['work'];identity=metrics['identity']
    lines=[f"Время: прогноз {rt['expected_seconds']:.3f} с; диапазон {rt['lower_seconds']:.3f}–{rt['upper_seconds']:.3f}; внутренний факт {rt['actual_seconds']:.3f} с; статус {rt['status']}.",
      'Полное время процесса проверяется по run.json; очередь и публикация отдельно. При выходе за диапазон сначала требуется разбор.',
      '',f"# E002d | {identity['run_id']} | {metrics['mode']}",
      f"Код: {identity['source_commit']}. Kernel SHA256: {metrics['environment']['kernel_sha256']}.",
      '', 'Вопрос: как независимые селективные дефазировочные воздействия меняют ток QS и RR относительно парного контроля?',
      'QS и RR сохраняют прежние H, скорости и начало: смесь |100;RRR>/|010;RRR>. Три узловых кубита, три рёберных qutrit; размер 216. Phi=epsilon=0, phi_n=.05; RK4.',
      'A: m2, rho[5,6]; B: m4, rho[3,6]. T: sqrt(gamma)(Pa-Pb)Qm; C: sqrt(gamma)(Pa+Pb)Qm. AB — сумма двух независимых диссипаторов.',
      'Основная доза .1; дополнительные .05/.2 только AB, SCREENING_ONLY. Основные сравнения проверяются dt=.01/.005. N=1 мониторируется, но отдельные воздействия в N=1 здесь не запускались.',
      f"Объём план/факт: {work}. Все провалы: {checks['failures']}.",
      'Состояние: trace/hermiticity<=1e-10, eigen>=-1e-8; dt: 1e-6+1e-4*scale. Стационарность: RHS<=1e-7, drift<=1e-6, диапазон F<=1e-8+1e-5|F|.',
      '', '|Случай|T|h окна|min/max h при t>0|стационарность|dt|',
      '|---|---:|---:|---|---|---|']
    for s in metrics['cases']:
        h=(s['reference'] or {}).get('h');x=s['h_extrema'];hs='нет окна' if h is None else f'{h:.9g}'
        lines.append(f"|{s['case']['id']}|{s['horizon']:g}|{hs}|{x[0]:.6g}@{x[1]:g}/{x[2]:.6g}@{x[3]:g}|{s['stationarity']['pass_gate']}|{s['refinement_status']}|")
    if metrics['mode']!='production':
        lines+=['','Это короткая техническая проверка. Стационарность и научный эффект по ней не оцениваются.']
    else:
        lines+=['','r_M=(hT-hC)/h0; Q=r_QS-r_RR. Отрицательное r означает уменьшение тока при целевом подавлении относительно контроля.',
          'Порог знака Q=1e-4+10|Q_fine-Q_coarse|. Это разрешение по шагу, не статистическая значимость.',
          '', '|Мишень|gamma|T|r_QS|r_RR|Q|статус|','|---|---:|---:|---:|---:|---:|---|']
        for row in metrics['analysis']['comparisons']:
            if row['evaluable']:
                lines.append(f"|{row['target']}|{row['gamma']:g}|{row['horizon']:g}|{row['models']['QS']['r']:.8g}|{row['models']['RR_QS']['r']:.8g}|{row['Q']:.8g}|{row['status']}|")
            else:lines.append(f"|{row['target']}|{row['gamma']:g}|{row['horizon']:g}|—|—|—|NOT_EVALUABLE|")
        lines+=['','Структурные сдвиги T−C, все секторные токи, веса масок/секторов и комплексные когерентности опубликованы в metrics.json и рядах.',
          'Для h_m,N различать сырой вклад, h_m,N/p_m и h_m,N/p_m,N; при весе<=1e-6 условное значение не определено. Сырые данные для обоих делений сохранены.']
    lines+=['','Полные экстремумы всех величин вычислены до разрежения: extrema.json. Ряды: series/, diagnostics/. Матрицы окон и все скаляры тех же времён: windows/.',
      'Числа текста округлены; NPZ/JSON сохраняют точность. Полные матрицы 216×216, полные ряды и контрольные точки остаются full/. Объём и SHA256 — data_manifest.json.',
      'Границы: эффект интервенции включает последующую перестройку структуры; он не доказывает необходимость запутанности, Фано или невозможность классического объяснения. Нулевой свидетель не доказывает сепарабельность. Научная приёмка остаётся за пользователем.']
    result='\n'.join(lines)+'\n'
    if len(result.encode())>24*1024:raise ValueError('Compact report exceeds 24 KiB')
    return result

def run(config,workdir=None):
    started=time.monotonic();root=Path.cwd() if workdir is None else Path(workdir)
    report=root/'report';full=root/'full';report.mkdir(parents=True,exist_ok=False);full.mkdir(parents=True,exist_ok=False)
    identity=dict(run_id=config['run_id'],source_commit=os.environ.get('VM_SOURCE_COMMIT',config.get('local_source_commit','LOCAL_TEST')))
    mode=config['mode'];runs=[];results=[];timings=[];fatal=None;extended=False
    try:
        plan=preflight(config);consequence=consequence_map()
        save_json(report/'intervention_map.json',consequence)
        for case in plan:
            print('START',case['id'],flush=True);t=time.monotonic()
            tr=Trajectory(case,full,disk_floor=0 if mode=='smoke' else 1.5*1024**3,builder=build)
            setup=time.monotonic()-t;t=time.monotonic();gate=tr.advance(case['horizon'])
            timings.append(dict(id=case['id'],model=case['model'],setup_seconds=setup,advance_seconds=time.monotonic()-t))
            runs.append(tr)
            print('DONE',case['id'],'stationary',gate['pass_gate'],flush=True)
        if mode=='production' and not all(tr.window and tr.completed_horizon==200. and
              stationarity(tr.window,200.)['pass_gate'] for tr in runs):
            extended=True
            for tr,timing in zip(runs,timings):
                t=time.monotonic();tr.advance(400.);timing['advance_seconds']+=time.monotonic()-t
        for tr,timing in zip(runs,timings):
            t=time.monotonic();r=tr.finish();timing['finish_seconds']=time.monotonic()-t
            timing.update(steps=tr.step,integrator_seconds=tr.integrator_seconds,diagnostic_seconds=tr.diagnostic_seconds)
            results.append(r)
    except Exception as exc:
        fatal=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
        save_json(full/'failure.json',fatal)
    analysis=analyze(results,mode);all_extrema={}
    (report/'windows').mkdir(exist_ok=True)
    for r in results:
        cid=r['summary']['case']['id'];all_extrema[cid]=export_case(report,r)
        r['summary']['h_extrema']=all_extrema[cid]['h_t_positive']
        ref=r['summary']['reference'];components=[]
        if ref is not None:
            for m in range(8):
                for n in (1,2):
                    p=ref[f'p_m{m}'];w=ref[f'p_m{m}_N{n}'];h=ref[f'h_m{m}_N{n}']
                    components.append(dict(mask=m,N=n,p_mask=p,p_mask_sector=w,h=h,
                        sector_fraction=w/p if p>1e-6 else None,h_given_mask=h/p if p>1e-6 else None,
                        h_given_mask_sector=h/w if w>1e-6 else None,
                        convention='ratios of window means; undefined when denominator<=1e-6'))
        r['summary']['sector_references']=components
        dtimes=r['diagnostics'][:,0];end=r['summary']['horizon']
        selected=np.ones(len(dtimes),bool) if mode!='production' else ((dtimes>=190)&(dtimes<=200))|((dtimes>=end-10)&(dtimes<=end))
        times=dtimes[selected];idx=[int(np.argmin(abs(r['series'][:,0]-t))) for t in times]
        np.savez_compressed(report/'windows'/f'{cid}.npz',time=times,blocks=r['certs']['blocks'][selected],
            scalar=r['series'][idx],diagnostics=r['diagnostics'][selected])
    planned=counts(mode,400. if extended else None);steps=sum(r['summary']['steps'] for r in results)
    volume=len(results)==planned['trajectories'] and steps==planned['steps'] and all(
        r['summary']['rhs_calls']==4*r['summary']['steps'] and
        r['summary']['scalar_records']==round(r['summary']['horizon']/.2)+1 and
        r['summary']['diagnostic_records']==int(r['summary']['horizon']//2)+1 for r in results)
    failures=([fatal['message']] if fatal else [])+([] if volume else ['work_volume_mismatch'])
    failures += [cid+':refinement_failed' for cid,pair in analysis['pairs'].items() if not pair['pass_gate']]
    baseline_checks=[]
    if mode=='production':
        for r in results:
            c=r['summary']['case']
            if c['target']!='base' or c['dt']!=.005:continue
            expected_h={'QS':.1098400932168605,'RR_QS':.0850336762}[c['model']]
            ref=integral_mean(r['series'],r['names'],200.)
            error=abs(ref['h']-expected_h) if ref else None
            passed=error is not None and error<=1e-6
            baseline_checks.append(dict(model=c['model'],expected_h=expected_h,actual_h=ref['h'] if ref else None,
                absolute_error=error,tolerance=1e-6,pass_gate=passed,
                source='E002c_WINDOW_EXPORT_v001_r001, fixed [190,200], h from published RESULT.md'))
            if not passed:failures.append(c['id']+':baseline_reproduction_failed')
    actual=time.monotonic()-started;f=config['forecast']
    if mode=='production':
        expected=f['fixed_seconds']+sum(f['seconds_per_step'][c['model']]*round((400. if extended else 200.)/c['dt']) for c in cases(mode))
        lo=.6*expected;hi=1.4*expected
    else:expected=f['expected_seconds'];lo=f['lower_seconds'];hi=f['upper_seconds']
    runtime=dict(expected_seconds=expected,lower_seconds=lo,upper_seconds=hi,actual_seconds=actual,
        status='PASS' if lo<=actual<=hi and volume and not fatal else 'REVIEW_REQUIRED',
        measured_interval='entry to before final report assembly; full process checked externally',
        branch='T400' if extended else mode+'_base',source=f.get('source'))
    metrics=dict(identity=identity,mode=mode,cases=[r['summary'] for r in results],analysis=analysis,
        work=dict(planned=planned,actual=dict(trajectories=len(results),steps=steps,rhs_calls=4*steps)),
        timing=timings,fatal=fatal,environment=dict(kernel_sha256=kernel_hash(),numpy=np.__version__,scipy=scipy.__version__,
            python=sys.version,platform=platform.platform(),threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')}))
    checks=dict(runtime_gate=runtime,work_volume_pass=bool(volume),baseline_reproduction=baseline_checks,failures=failures,
        technical_status='FAILED' if failures else 'PASS',scientific_acceptance='USER_REVIEW_REQUIRED')
    if results:save_json(report/'schema.json',dict(series=['time']+results[0]['names'],diagnostics=['time']+results[0]['dnames'],
        states=['unconditional']+[f'mask_{m}' for m in range(8)],node_basis='000,001,010,011,100,101,110,111',
        mask_bits=['01','12','02'],window='six even-time points in [T-10,T], plus [190,200] if extended; short diagnostic grid for calibration'))
    save_json(report/'config.json',config);save_json(report/'metrics.json',metrics);save_json(report/'checks.json',checks)
    save_json(report/'extrema.json',all_extrema)
    (report/'RESULT.md').write_text(compact(metrics,checks));(report/'README.md').write_text('E002d: RESULT.md, metrics.json, checks.json, schema.json; exact window blocks in windows/.\n')
    write_manifest(report,full)
    if not fatal:
        from .verify import verify
        verification=verify(report);save_json(report/'verification.json',verification);write_manifest(report,full)
    print(json.dumps(dict(runtime=runtime,work=metrics['work'],failures=failures),ensure_ascii=False),flush=True)
    if failures:raise RuntimeError('; '.join(failures))
    return metrics,checks
