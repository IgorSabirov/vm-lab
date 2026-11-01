"""Recompute finite-window scientific results from exported arrays."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .core import analyze, prepare
from .plan import PROTOCOL, workload, protocol_hash, implementation_hash, implementation_manifest, cases
from .reporting import render_result


def numeric_equal(a,b,atol=1e-13,rtol=1e-12):
    if isinstance(a,dict) and isinstance(b,dict):
        return a.keys()==b.keys() and all(numeric_equal(a[k],b[k],atol,rtol) for k in a)
    if isinstance(a,list) and isinstance(b,list):
        return len(a)==len(b) and all(numeric_equal(x,y,atol,rtol) for x,y in zip(a,b))
    if isinstance(a,bool) or isinstance(b,bool) or a is None or b is None:
        return type(a) is type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        return bool(np.isfinite([a,b]).all() and np.isclose(a,b,atol=atol,rtol=rtol))
    return a==b


def verify_full_files(report,full):
    """Optional local VM audit; never fetches an unpublished archive."""
    full = Path(full)
    manifest = json.loads((report/'full_manifest.json').read_text())
    expected = {e['path'] for e in manifest['files']}
    if len(expected) != len(manifest['files']) or expected != {p.relative_to(full).as_posix() for p in full.rglob('*') if p.is_file()}:
        raise ValueError('Full archive coverage mismatch')
    for e in manifest['files']:
        rel = Path(e['path'])
        if rel.is_absolute() or '..' in rel.parts or '.tmp' in rel.name:
            raise ValueError('Unsafe full archive path')
        data = (full/rel).read_bytes()
        if len(data)!=e['size'] or hashlib.sha256(data).hexdigest()!=e['sha256']:
            raise ValueError('Full archive checksum mismatch')
    if manifest['total_bytes'] != sum(e['size'] for e in manifest['files']):
        raise ValueError('Full archive byte total mismatch')


def verify_report(report, full=None, model_factory=None):
    report = Path(report)
    if json.loads((report/'status.json').read_text()).get('status') != 'COMPLETED_NOT_ACCEPTED':
        raise ValueError('Failed/incomplete run cannot be verified')
    manifest = json.loads((report/'manifest.json').read_text())
    names = [e['path'] for e in manifest['files']]
    if len(names) != len(set(names)) or set(names) != {p.name for p in report.iterdir() if p.is_file() and p.name != 'manifest.json'}:
        raise ValueError('Manifest coverage mismatch')
    for entry in manifest['files']:
        p = Path(entry['path'])
        if p.name != str(p) or p.is_absolute():
            raise ValueError('Unsafe report path')
        data = (report/p).read_bytes()
        if len(data) != entry['size'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('Report checksum mismatch')
    if manifest['total_bytes'] != sum(e['size'] for e in manifest['files']):
        raise ValueError('Manifest byte total mismatch')
    cfg = json.loads((report/'config.json').read_text()); mode = cfg['mode']
    if mode not in ('calibration', 'production'):
        raise ValueError('Unsupported report mode')
    horizon = PROTOCOL['horizon'] if mode == 'production' else PROTOCOL['calibration_horizon']
    metrics = json.loads((report/'metrics.json').read_text())
    if json.loads((report/'dependencies.json').read_text()) != implementation_manifest():
        raise ValueError('Dependency manifest mismatch')
    if (cfg.get('protocol_sha256') != protocol_hash() or cfg.get('implementation_sha256') != implementation_hash()
            or metrics.get('protocol_sha256') != cfg['protocol_sha256']
            or metrics.get('implementation_sha256') != cfg['implementation_sha256']
            or metrics.get('source_commit') != cfg['source_commit']):
        raise ValueError('Report source/protocol/implementation mismatch')
    if metrics['actual_counts'] != workload(horizon):
        raise ValueError('Workload mismatch')
    records = list(report.glob('*_case.json'))
    if len(records) != 3:
        raise ValueError('Missing case')
    models = set(); expected_cases = {c['id']:c for c in cases()}; primaries = {}; parsed = []
    if full is not None:
        verify_full_files(report,full)
    for path in records:
        r = json.loads(path.read_text()); models.add(r['case']['model']); parsed.append(r)
        if r['id'] not in expected_cases or r['case'] != expected_cases[r['id']]:
            raise ValueError('Report case identity/physics mismatch')
        if r['hilbert_dimension'] != int(np.prod(PROTOCOL['dimensions'])):
            raise ValueError('Report Hilbert dimension mismatch')
        result = r['result']
        if full is not None and mode == 'production':
            if model_factory is None:
                from e002e_exp.model import make_full
                model_factory = lambda case:make_full(case,assemble=False)
            model = model_factory(r['case'])
            with np.load(Path(full)/r['id']/'initial.npz',allow_pickle=False) as archive:
                for label,key in (('primary','preparation'),('independent','reference_preparation')):
                    initial = archive[label]
                    reconstructed,prep = prepare(model,initial[:,0],tuple(PROTOCOL['dimensions']),PROTOCOL['operator_tolerance'])
                    if not np.array_equal(initial,reconstructed):
                        raise ValueError('Full initial product reconstruction mismatch')
                    if not numeric_equal(prep,{k:result[key][k] for k in prep}):
                        raise ValueError('Full preparation diagnostics mismatch')
        if not r['numerical']['comparison']['pass_gate'] or any(not c['quality']['pass'] for c in r['numerical']['checks']):
            raise ValueError('Failed numerical state checks')
        with np.load(report/(r['id']+'_series.npz'), allow_pickle=False) as data:
            runs = []
            for label in ('fine', 'coarse', 'reference'):
                run = {n:data[label+'_'+n] for n in ('time','time_index','dt','flux','sample_time','sample_index','raw')}
                run['names'] = tuple(data['names'].tolist())
                if not np.isfinite(run['raw']).all() or abs(run['time'][-1]-horizon) > 1e-12:
                    raise ValueError('Invalid exported time grid/data')
                dt = PROTOCOL['dt_coarse'] if label == 'coarse' else PROTOCOL['dt_fine']
                expected = np.arange(round(horizon/dt)+1)*dt
                indices = np.arange(len(expected)); sample_indices = indices[::round(PROTOCOL['sample_interval']/dt)]
                if (run['time_index'].dtype.kind not in 'iu' or run['sample_index'].dtype.kind not in 'iu'
                        or not np.array_equal(run['time_index'],indices) or not np.array_equal(run['sample_index'],sample_indices)
                        or float(run['dt']) != dt):
                    raise ValueError('Integration index/dt contract mismatch')
                if run['time'].shape != expected.shape or not np.allclose(run['time'],expected,rtol=0.,atol=1e-12):
                    raise ValueError('Missing or altered integration samples')
                sample_expected = expected[::round(PROTOCOL['sample_interval']/dt)]
                if run['sample_time'].shape != sample_expected.shape or not np.allclose(run['sample_time'],sample_expected,rtol=0.,atol=1e-12):
                    raise ValueError('Missing or altered observable samples')
                checks = json.loads((report/(r['id']+'_'+label+'_physicality.json')).read_text())
                expected_check_time = expected[::round(PROTOCOL['physicality_interval']/dt)].tolist()
                if len(checks)!=len(expected_check_time) or not np.allclose([c['time'] for c in checks],expected_check_time,rtol=0.,atol=1e-12):
                    raise ValueError('Physicality checkpoint coverage mismatch')
                for c in checks:
                    if len(c['states']) != 2:
                        raise ValueError('Missing physicality state')
                    for s in c['states']:
                        if (s.get('psd_mode')!='FULL_HILBERT'
                                or not np.isfinite([s[k] for k in ('trace_error','hermiticity','minimum_eigenvalue')]).all()
                                or s['trace_error'] > PROTOCOL['state_tolerance']
                                or s['hermiticity'] > PROTOCOL['state_tolerance']
                                or s['minimum_eigenvalue'] < -PROTOCOL['state_tolerance']):
                            raise ValueError('Physicality failed')
                runs.append(run)
            check = analyze(*runs, baseline_flux=r['baseline'][0]['F'], reference_flux=r['baseline'][1]['F'], policy=PROTOCOL)
            for key in ('area_absolute','area_uncertainty','signed_area','peak_relative','time_peak','final_delta_flux',
                        'sham_drift','reference_sham_drift','coarse_sham_drift'):
                if not np.isfinite(result[key]) or not np.isclose(result[key], check[key], atol=1e-13, rtol=1e-12):
                    raise ValueError('Derived metric mismatch: '+key)
            if not np.allclose(data['raw_uncertainty'], check['raw_uncertainty'], atol=1e-15, rtol=1e-12):
                raise ValueError('Primitive uncertainty mismatch')
            if not numeric_equal(result['conditional'],check['conditional']):
                raise ValueError('Conditional h/p or null policy mismatch')
            if mode == 'production':
                if not numeric_equal(result['primary'],check['primary']):
                    raise ValueError('Primary interval/verdict mismatch')
                primaries[r['case']['model']] = result['primary']
                if any(abs(run['flux'][0,0]-run['flux'][0,1]) > PROTOCOL['operator_tolerance'] for run in runs):
                    raise ValueError('Initial local flux was not preserved')
                for p in (result['preparation'], result['reference_preparation']):
                    errors = list(p['marginal_errors'].values())+list(p['sector_errors'].values())
                    if not np.isfinite(errors).all() or max(errors) > PROTOCOL['operator_tolerance']:
                        raise ValueError('Preparation violated marginal contract')
                    if p['universal_cptp_channel'] is not False or p['sector_contract'] != PROTOCOL['sector_contract']:
                        raise ValueError('Preparation semantics mismatch')
                    if r['hilbert_dimension']==216:
                        b=p['output_balance']
                        if (b['status']!='OPERATOR_IDENTITY_VERIFIED'
                                or b['residual']>PROTOCOL['operator_tolerance']
                                or abs(p['delta_flux_derivative_at_zero']-b['kappa_out']*p['delta_h_at_zero'])>PROTOCOL['operator_tolerance']):
                            raise ValueError('Initial balance diagnostics mismatch')
            elif 'primary' in result or result['preparation']['status'] != 'KNOWN_BASELINE_SHAM_ONLY_NO_NEW_INTERVENTION':
                raise ValueError('Calibration exposed a scientific verdict')
    if models != set(PROTOCOL['models']):
        raise ValueError('Model coverage mismatch')
    comparisons = json.loads((report/'comparisons.json').read_text())
    if mode == 'production':
        if len(comparisons) != 2 or {c['comparison'] for c in comparisons} != {'QS_minus_RR_QS','QS_minus_IC1_QS'}:
            raise ValueError('Comparative coverage mismatch')
        for c in comparisons:
            other = primaries[c['comparison'].removeprefix('QS_minus_')]; q = primaries['QS']
            v = q['value']-other['value']; u=q['uncertainty']+other['uncertainty']
            if not numeric_equal([c['delta_relative_response'],c['uncertainty'],c['interval']],[v,u,[v-u,v+u]]):
                raise ValueError('Comparative metric mismatch')
    elif comparisons:
        raise ValueError('Calibration must not assign comparative scientific effects')
    expected_text = render_result(cfg,metrics,parsed)
    if any((report/name).read_text()!=expected_text for name in ('RESULT.md','README.md')):
        raise ValueError('Human report differs from numerical records')
    return dict(status='REPORT_HASHES_METRICS_CONDITIONALS_AND_VERDICTS_VERIFIED', models=sorted(models),
                full_states='INITIAL_PREPARATION_RECONSTRUCTED' if full is not None and mode=='production' else 'NOT_READ',
                runtime='ENCLOSING_SERVICE_RUN_JSON_REQUIRES_SEPARATE_REVIEW')
