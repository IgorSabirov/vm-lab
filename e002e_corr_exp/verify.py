"""Recompute finite-window scientific results from exported arrays."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .core import analyze
from .plan import PROTOCOL, workload, protocol_hash, implementation_hash, cases


def verify_report(report):
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
    models = set(); expected_cases = {c['id']:c for c in cases()}; primaries = {}
    for path in records:
        r = json.loads(path.read_text()); models.add(r['case']['model'])
        if r['id'] not in expected_cases or r['case'] != expected_cases[r['id']]:
            raise ValueError('Report case identity/physics mismatch')
        if r['hilbert_dimension'] != int(np.prod(PROTOCOL['dimensions'])):
            raise ValueError('Report Hilbert dimension mismatch')
        result = r['result']
        if not r['numerical']['comparison']['pass_gate'] or any(not c['quality']['pass'] for c in r['numerical']['checks']):
            raise ValueError('Failed numerical state checks')
        with np.load(report/(r['id']+'_series.npz'), allow_pickle=False) as data:
            runs = []
            for label in ('fine', 'coarse', 'reference'):
                run = {n:data[label+'_'+n] for n in ('time', 'flux', 'sample_time', 'raw')}
                run['names'] = tuple(data['names'].tolist())
                if not np.isfinite(run['raw']).all() or abs(run['time'][-1]-horizon) > 1e-12:
                    raise ValueError('Invalid exported time grid/data')
                dt = PROTOCOL['dt_coarse'] if label == 'coarse' else PROTOCOL['dt_fine']
                expected = np.arange(round(horizon/dt)+1)*dt
                if not np.array_equal(run['time'], expected):
                    raise ValueError('Missing or altered integration samples')
                sample_expected = expected[::round(PROTOCOL['sample_interval']/dt)]
                if not np.array_equal(run['sample_time'], sample_expected):
                    raise ValueError('Missing or altered observable samples')
                checks = json.loads((report/(r['id']+'_'+label+'_physicality.json')).read_text())
                expected_check_time = expected[::round(PROTOCOL['physicality_interval']/dt)].tolist()
                if [c['time'] for c in checks] != expected_check_time:
                    raise ValueError('Physicality checkpoint coverage mismatch')
                for c in checks:
                    if len(c['states']) != 2:
                        raise ValueError('Missing physicality state')
                    for s in c['states']:
                        if (not np.isfinite(list(s.values())).all() or s['trace_error'] > PROTOCOL['state_tolerance']
                                or s['hermiticity'] > PROTOCOL['state_tolerance']
                                or s['minimum_eigenvalue'] < -PROTOCOL['state_tolerance']):
                            raise ValueError('Physicality failed')
                runs.append(run)
            check = analyze(*runs, baseline_flux=r['baseline'][0]['F'], reference_flux=r['baseline'][1]['F'], policy=PROTOCOL)
            for key in ('area_absolute', 'area_uncertainty', 'signed_area', 'peak_relative', 'time_peak', 'final_delta_flux', 'sham_drift'):
                if not np.isfinite(result[key]) or not np.isclose(result[key], check[key], atol=1e-13, rtol=1e-12):
                    raise ValueError('Derived metric mismatch: '+key)
            if not np.allclose(data['raw_uncertainty'], check['raw_uncertainty'], atol=1e-15, rtol=1e-12):
                raise ValueError('Primitive uncertainty mismatch')
            if result['conditional'] != check['conditional']:
                raise ValueError('Conditional h/p or null policy mismatch')
            if mode == 'production':
                if result['primary'] != check['primary']:
                    raise ValueError('Primary interval/verdict mismatch')
                primaries[r['case']['model']] = result['primary']
                if abs(runs[0]['flux'][0,0]-runs[0]['flux'][0,1]) > PROTOCOL['operator_tolerance']:
                    raise ValueError('Initial local flux was not preserved')
                for p in (result['preparation'], result['reference_preparation']):
                    if max(p['marginal_errors'].values()) > PROTOCOL['operator_tolerance']:
                        raise ValueError('Preparation violated marginal contract')
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
            if c['delta_relative_response'] != v or c['uncertainty'] != u or c['interval'] != [v-u,v+u]:
                raise ValueError('Comparative metric mismatch')
    elif comparisons:
        raise ValueError('Calibration must not assign comparative scientific effects')
    return dict(status='REPORT_HASHES_METRICS_CONDITIONALS_AND_VERDICTS_VERIFIED', models=sorted(models),
                full_states='NOT_READ', runtime='ENCLOSING_SERVICE_RUN_JSON_REQUIRES_SEPARATE_REVIEW')
