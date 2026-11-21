"""Independent reconstruction and optional native replay of P9 ACT/SPT outputs.

Saved absolute paths are provenance only. Relocated bundles are consumed from
their registered engine/corner/accuracy directory under the audited P9 root.
The fixed-spectrum interface cannot close common cosmological optimization.
"""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import tempfile

import numpy as np

from .common import InputError, canonical_hash, finite, read_json, sha256
from .external_cmb import ACT, SPT, DONOR_REGISTRY, LOCK, required_lmax, to_dl, isolated_batch

ENGINES = ('linx', 'primat')
CORNERS = ('00', '10', '01', '11full', '11add')
ADAPTER = Path(__file__).with_name('external_cmb.py')
REQUEST_KEYS = {'cache', 'offline', 'variants', 'nuisance', 'profile_nuisance',
                'profile_policy', 'spt_tau_prior'}
DATA_KEYS = {
    ACT: ('act-implementation', 'act-release'),
    SPT: ('spt-SPT3G_D1_TnE_lite.yaml', 'spt-SPT3G_D1_TnE_lite_bdp.txt',
          'spt-SPT3G_D1_TnE_lite_cov.txt', 'spt-TT_lxl_window_functions.txt',
          'spt-TE_lxl_window_functions.txt', 'spt-EE_lxl_window_functions.txt'),
}


def _equal(actual, expected, name, *, atol=1e-10):
    if not math.isclose(float(actual), float(expected), rel_tol=1e-11, abs_tol=atol):
        raise InputError(f'external CMB {name} does not follow the saved primary inputs')


def _layout(root, config):
    levels = config.get('class_refinement')
    if levels is not None:
        from .backends import validate_class_refinement
        levels = validate_class_refinement(levels)
    count = len(levels) if levels else 1
    tasks, groups = {}, {}
    for engine in ENGINES:
        for corner in CORNERS:
            key = f'{engine}/{corner}'
            groups[key] = []
            for index in range(count):
                final = index == count - 1
                tag = key if final else f'{key}@accuracy{index}'
                directory = root/'class'/engine/(corner if final else f'{corner}.accuracy-{index}')
                tasks[tag] = directory
                groups[key].append(tag)
    return tasks, groups, levels


def _priors(record, variant, cosmology, request):
    values = record.get('nuisance', {})
    if variant == ACT:
        expected = {'A_act': {'kind': 'uniform', 'bounds': [.5, 1.5], 'included': True},
                    'P_act': {'kind': 'uniform', 'bounds': [.9, 1.1], 'included': True}}
        if set(values) != set(expected) or any(not x['bounds'][0] <= finite(values[k], k) <= x['bounds'][1]
                                               for k, x in expected.items()):
            raise InputError('ACT nuisance vector lies outside the pinned prior policy')
        penalty = 0.
    else:
        if request.get('spt_tau_prior') not in ('include', 'omit'):
            raise InputError('SPT optical-depth prior policy is missing')
        if set(values) != {'Tcal', 'Ecal'}:
            raise InputError('SPT nuisance vector is incomplete or has an invented parameter')
        for k, v in values.items():
            finite(v, k, positive=True)
        tau = finite(cosmology.get('tau_reio'), 'spectrum optical depth', nonnegative=True)
        expected = {'tau': {'kind': 'Gaussian_unnormalized', 'mean': .051, 'sigma': .006,
                            'value': tau, 'included': request['spt_tau_prior'] == 'include'},
                    'Tcal': {'kind': 'Gaussian_unnormalized', 'mean': 1., 'sigma': .00360,
                             'value': values['Tcal'], 'included': True}}
        penalty = -sum(.5*((x['value'] - x['mean'])/x['sigma'])**2
                       for x in expected.values() if x['included'])
    if canonical_hash(record.get('priors')) != canonical_hash(expected):
        raise InputError('external CMB prior vector differs from the pinned policy or same-spectrum tau')
    _equal(record['log_prior'], penalty, 'prior arithmetic')
    _equal(record['log_posterior'], finite(record['logL'], 'data log likelihood') + penalty,
           'posterior arithmetic')


def _producer(directory, original_task, required, precision):
    path, proof_path = directory/'spectra.json', directory/'receipt.json'
    task = deepcopy(original_task)
    if sha256(path) != task['sha256'] or sha256(proof_path) != task['producer_receipt']['sha256']:
        raise InputError('relocated external CMB spectrum or producer receipt changed')
    spectra, proof = read_json(path), read_json(proof_path)
    if proof.get('spectra_sha256') != task['sha256']:
        raise InputError('producer receipt belongs to another spectrum')
    parameters = proof.get('input', {}).get('parameters', {})
    cosmology = task.get('cosmology', {})
    if 'tau_reio' not in parameters or cosmology.get('tau_reio') != parameters['tau_reio']:
        raise InputError('external CMB tau differs from its actual CLASS input')
    if any(k not in parameters or v != parameters[k] for k, v in cosmology.items()):
        raise InputError('external CMB cosmology differs from its actual CLASS input')
    to_dl(spectra, lmax=required)
    if proof.get('input', {}).get('l_max_scalars') != spectra['ell'][-1]:
        raise InputError('CLASS receipt and delivered multipole coverage disagree')
    if precision is not None and proof.get('input', {}).get('precision') != precision:
        raise InputError('CLASS refinement did not execute the registered accuracy settings')
    missing = []
    files = proof.get('files', {})
    if not files or files.get('spectra.json') != task['sha256']:
        raise InputError('CLASS receipt lacks its original output inventory')
    for name, digest in files.items():
        member = directory/name
        if Path(name).name != name or not member.resolve().is_relative_to(directory.resolve()):
            raise InputError('CLASS receipt contains a path outside its own directory')
        if not member.is_file():
            missing.append(str(member.relative_to(directory)))
        elif sha256(member) != digest:
            raise InputError('original CLASS output differs from the producer inventory')
    ini = directory/'parameters.ini'
    helium = None
    if ini.is_file():
        if sha256(ini) != proof.get('parameters_sha256'):
            raise InputError('CLASS parameter file differs from its execution receipt')
        pars = dict(line.split('=', 1) for line in ini.read_text().splitlines() if '=' in line)
        pars = {k.strip(): v.strip() for k, v in pars.items()}
        if pars.get('lensing') != 'yes' or pars.get('format') != 'camb':
            raise InputError('native producer did not request lensed CAMB-format spectra')
        _equal(pars.get('tau_reio'), cosmology['tau_reio'], 'actual parameter-file optical depth')
        _equal(pars.get('l_max_scalars'), spectra['ell'][-1], 'actual parameter-file ell coverage')
        for key, value in {**parameters, **proof['input'].get('precision', {})}.items():
            if isinstance(value, str):
                if pars.get(key) != value:
                    raise InputError('CLASS input option differs from the actual parameter file')
            else:
                _equal(pars.get(key), value, 'actual parameter-file '+key, atol=1e-16)
        helium = finite(pars.get('YHe'), 'CLASS helium mass fraction', positive=True)
    else:
        missing.append('parameters.ini')
    raw = [directory/n for n in files if n.endswith('cl_lensed.dat')]
    if len(raw) != 1:
        raise InputError('CLASS receipt must name one original lensed spectrum')
    if raw[0].is_file():
        table = np.loadtxt(raw[0])
        ell = np.asarray(spectra['ell'])
        if table.ndim != 2 or table.shape[1] < 5 or not np.array_equal(table[:, 0], ell):
            raise InputError('raw CLASS lensed spectrum has different multipole coverage')
        factor = 2*np.pi/(ell*(ell + 1))
        for index, key in enumerate(('TT', 'EE', 'BB', 'TE'), 1):
            if not np.allclose(table[:, index]*factor, spectra[key], rtol=1e-12, atol=1e-14):
                raise InputError('delivered Cl do not reproduce the native CAMB-format lensed data')
    task['path'] = str(path.resolve())
    task['producer_receipt']['path'] = str(proof_path.resolve())
    common = deepcopy(proof.get('input', {}))
    common.pop('precision', None)
    common.update(YHe=helium, matching=proof.get('matching'),
                  source_P7_history_sha256=proof.get('source_P7_history_sha256'))
    return task, spectra, missing, canonical_hash(common)


def _release_receipts(result, request):
    catalog, lock = read_json(DONOR_REGISTRY), read_json(LOCK)
    receipts = result.get('receipt', {})
    if set(receipts) != set(request['variants']):
        raise InputError('external CMB data receipt omits or adds a likelihood variant')
    for variant, receipt in receipts.items():
        count = receipt.get('actual_evaluations')
        if not isinstance(count, int) or isinstance(count, bool) or count < len(request['spectra']):
            raise InputError('external CMB receipt does not establish evaluation of every requested spectrum')
        expected = {name: {k: catalog[name][k] for k in ('url', 'bytes', 'sha256')}
                    for name in DATA_KEYS[variant]}
        if receipt.get('data_sources') != expected or receipt.get('variant') != variant:
            raise InputError('external CMB release differs from the pinned data registry')
        env = receipt.get('environment', {})
        if (env.get('lock_sha256') != sha256(LOCK) or env.get('packages') != lock['packages']
                or env.get('platform') != lock['platform'] or receipt.get('adapter_sha256') != sha256(ADAPTER)):
            raise InputError('external CMB runtime or adapter receipt does not match the validated lock')
        if receipt.get('required_lmax') != required_lmax([variant]):
            raise InputError('external CMB receipt has an unregistered multipole cut')
        if variant == ACT:
            windows = {pol: {'minimum': 2, 'maximum': 8501, 'selected_bins': 45} for pol in ('tt', 'te', 'ee')}
            shape = [135, 135]
        else:
            windows = {pol: {'minimum': 2, 'maximum': 4095, 'bins': 52 if pol == 'TT' else 72}
                       for pol in ('TT', 'TE', 'EE')}
            shape = [196, 196]
        validation = receipt.get('covariance_validation', {})
        if (receipt.get('windows') != windows or validation.get('shape') != shape
                or validation.get('symmetrized') is not False
                or not 0 <= finite(validation.get('normalized_max_asymmetry'), 'covariance asymmetry') <= 1e-8
                or finite(validation.get('minimum_Cholesky_diagonal'), 'Cholesky pivot') <= 0):
            raise InputError('external CMB mask/windows/covariance policy differs from the validated release')
        if receipt.get('spt_tau_prior') != request.get('spt_tau_prior'):
            raise InputError('external CMB data receipt has another optical-depth prior policy')


def audit_external_cmb(root, config, replay_config=None, workdir=None):
    """Check every requested P9 task and replay native code in a fresh directory.

    Returns OPEN_INPUT for missing requested output, PARTIAL for valid numerical
    evidence with outstanding inference requirements, and NOT_REQUESTED only
    when the stage did not select this interface. Tampered evidence raises.
    """
    policy = config.get('external_cmb')
    if policy is None:
        return {'status': 'NOT_REQUESTED', 'remaining': []}
    root = Path(root).resolve()
    required = required_lmax(policy.get('variants', []))
    filenames = ('external_cmb_request.json', 'external_cmb_evaluations.json', 'external_cmb_convergence.json')
    missing = [name for name in filenames if not (root/name).is_file()]
    if missing:
        return {'status': 'OPEN_INPUT', 'remaining': ['EXTERNAL_CMB_MISSING: '+name for name in missing]}
    request, result, gates = [read_json(root/name) for name in filenames]
    original_request_sha = canonical_hash(request)
    if result.get('request_sha256') != original_request_sha:
        raise InputError('external CMB result belongs to another original request')
    expected_policy = {k: v for k, v in policy.items() if k in REQUEST_KEYS}
    if {k: request[k] for k in REQUEST_KEYS if k in request} != expected_policy:
        raise InputError('external CMB request changed the registered likelihood prescription')
    if (request.get('adapter_sha256') != sha256(ADAPTER)
            or set(request) != set(expected_policy) | {'spectra', 'adapter_sha256', 'mode'}
            or request.get('mode') != config.get('_mode', 'conditional')):
        raise InputError('external CMB request has an unregistered adapter, mode or option')
    if (result.get('schema') != 'R135-external-CMB-evaluations-v1'
            or result.get('combination', {}).get('status') != 'SEPARATE_ALTERNATIVES'
            or result.get('combination', {}).get('joint_logL') is not None
            or result.get('cosmological_optimization') != 'NOT_PERFORMED'
            or result.get('confidence_calibrated') is not False):
        raise InputError('fixed-spectrum alternatives cannot claim a joint calibrated cosmological fit')
    tasks, groups, levels = _layout(root, config)
    if set(request.get('spectra', {})) != set(tasks) or set(result.get('evaluations', {})) != set(tasks):
        raise InputError('external CMB omitted or added an engine/corner/accuracy task')
    missing = [str((directory/name).relative_to(root)) for directory in tasks.values()
               for name in ('spectra.json', 'receipt.json') if not (directory/name).is_file()]
    if missing:
        return {'status': 'OPEN_INPUT', 'remaining': ['EXTERNAL_CMB_MISSING: '+name for name in missing]}
    _release_receipts(result, request)
    rebased, remaining, raw_missing, physics = deepcopy(request), [], [], {}
    for tag, directory in tasks.items():
        if not directory.resolve().is_relative_to(root):
            raise InputError('external CMB producer directory resolves outside the audited bundle')
        group = tag.split('@')[0]
        index = groups[group].index(tag)
        task, spectra, omitted, signature = _producer(directory, request['spectra'][tag], required,
                                                        levels[index] if levels else None)
        if group in physics and physics[group] != signature:
            raise InputError('CLASS accuracy refinement changed its physical inputs')
        physics[group] = signature
        raw_missing.extend(f'{tag}/{name}' for name in omitted)
        rebased['spectra'][tag] = task
        records = result['evaluations'][tag]
        if set(records) != set(request['variants']):
            raise InputError('external CMB omitted or added a likelihood at one required point')
        for variant, record in records.items():
            if (record.get('spectra_sha256') != canonical_hash(spectra)
                    or record.get('consumed_file_sha256') != task['sha256']
                    or record.get('producer_receipt') != request['spectra'][tag]['producer_receipt']
                    or record.get('cosmology_sha256') != canonical_hash(task['cosmology'])
                    or record.get('variant') != variant or record.get('support') is not True
                    or record.get('cosmological_optimization') != 'NOT_PERFORMED'
                    or record.get('confidence_calibrated') is not False):
                raise InputError('external CMB answer is not bound to the consumed spectrum and cosmology')
            _priors(record, variant, task['cosmology'], request)
            if request.get('profile_nuisance', False):
                profile = record.get('profile', {})
                if (profile.get('status') != 'PROFILED_FIXED_COSMOLOGY' or profile.get('method') != 'Powell'
                        or profile.get('cosmological_optimization') != 'NOT_PERFORMED'
                        or profile.get('confidence_calibrated') is not False):
                    raise InputError('external CMB nuisance profile did not complete its declared method')
                profile_policy = request.get('profile_policy') or {}
                bounds = ({'A_act': [.5, 1.5], 'P_act': [.9, 1.1]} if variant == ACT else
                          {'Tcal': [.01, 2.], 'Ecal': profile_policy.get('spt_ecal_bounds')})
                if profile.get('bounds') != bounds:
                    raise InputError('external CMB nuisance optimizer changed its registered domain')
                best = profile.get('best', {})
                for name in ('nuisance', 'logL', 'log_prior', 'log_posterior'):
                    if record.get(name) != best.get(name):
                        raise InputError('external CMB best nuisance point differs from its evaluation')
                attempts = profile.get('attempts', [])
                expected_count = len(profile_policy.get('starts', {}).get(variant, [{}]))
                if len(attempts) != expected_count:
                    raise InputError('external CMB nuisance optimizer omitted a registered start')
                successful = [r for r in attempts if r.get('success') and r.get('support')]
                if not successful or best['log_posterior'] != max(r['log_posterior'] for r in successful):
                    raise InputError('external CMB profiler did not retain its best successful start')
                for attempt in attempts:
                    _priors(attempt, variant, task['cosmology'], request)
                    if (attempt.get('spectra_sha256') != record['spectra_sha256']
                            or attempt.get('cosmology_sha256') != record['cosmology_sha256']):
                        raise InputError('nuisance optimization changed its fixed spectrum or cosmology')
            else:
                defaults = {'A_act': 1., 'P_act': 1.} if variant == ACT else {'Tcal': 1., 'Ecal': 1.}
                if record.get('nuisance') != request.get('nuisance', {}).get(variant, defaults):
                    raise InputError('external CMB fixed nuisance vector changed between request and result')
    checked_gates = {}
    if levels:
        for key, tags in groups.items():
            for variant in request['variants']:
                name = f'{key}/{variant}'
                tolerance = policy.get('max_delta_logL', config.get('max_cmb_delta_logL'))
                if isinstance(tolerance, dict):
                    tolerance = tolerance.get(variant)
                tolerance = finite(tolerance, 'registered external CMB accuracy tolerance', positive=True)
                values = [result['evaluations'][tag][variant]['log_posterior'] for tag in tags]
                changes = np.abs(np.diff(values)).tolist()
                expected = {'status': 'PASS' if max(changes) <= tolerance else 'FAIL_CMB_CONVERGENCE',
                            'logL_by_accuracy': values, 'adjacent_delta_logL': changes, 'max_delta_logL': tolerance}
                if gates.get(name) != expected:
                    raise InputError('external CMB convergence gate differs from the actual refined evaluations')
                checked_gates[name] = expected
        if set(gates) != set(checked_gates):
            raise InputError('external CMB convergence table has missing or extra points')
        if any(g['status'] != 'PASS' for g in checked_gates.values()):
            remaining.append('EXTERNAL_CMB_CLASS_REFINEMENT_FAILED')
    else:
        if gates.get('status') != 'NOT_VALIDATED':
            raise InputError('one CLASS setting cannot establish external CMB convergence')
        remaining.append('EXTERNAL_CMB_CLASS_REFINEMENT_NOT_PERFORMED')
    native_replay = None
    runtime = (replay_config or {}).get('external_cmb', {})
    ready = all(runtime.get(k) for k in ('python', 'python_sha256', 'cache'))
    if ready and Path(runtime['python']).is_file() and Path(runtime['cache']).is_dir():
        rebased['cache'], rebased['offline'] = str(Path(runtime['cache']).resolve()), True
        cache_missing = [s['sha256'] for receipt in result['receipt'].values()
                         for s in receipt['data_sources'].values()
                         if not (Path(rebased['cache'])/s['sha256']).is_file()]
        if cache_missing:
            remaining.append('EXTERNAL_CMB_PINNED_REPLAY_DATA_UNAVAILABLE')
        else:
            parent = Path(workdir) if workdir else root/'audit_native_replay'
            parent.mkdir(parents=True, exist_ok=True)
            fresh = Path(tempfile.mkdtemp(prefix='external-cmb-', dir=parent))
            native_replay = isolated_batch(rebased, runtime['python'], fresh,
                                           interpreter_sha256=runtime['python_sha256'])
            for tag in tasks:
                for variant in request['variants']:
                    old, new = result['evaluations'][tag][variant], native_replay['evaluations'][tag][variant]
                    for key in ('logL', 'log_prior', 'log_posterior'):
                        _equal(new[key], old[key], 'independent native '+key, atol=1e-7)
                    for key in old['nuisance']:
                        _equal(new['nuisance'][key], old['nuisance'][key], 'independent native nuisance', atol=1e-7)
            for variant in request['variants']:
                for key in ('covariance_sha256', 'windows', 'data_sources', 'required_lmax', 'spt_tau_prior'):
                    if native_replay['receipt'][variant][key] != result['receipt'][variant][key]:
                        raise InputError('native replay consumed another covariance, mask or data release')
    else:
        remaining.append('EXTERNAL_CMB_PINNED_NATIVE_REPLAY_UNAVAILABLE')
    remaining.extend(['EXTERNAL_CMB_COMMON_COSMOLOGY_OPTIMIZATION_NOT_PERFORMED',
                      'EXTERNAL_CMB_CONFIDENCE_CALIBRATION_NOT_PERFORMED'])
    remaining.extend('EXTERNAL_CMB_RAW_OUTPUT_MISSING: '+name for name in raw_missing)
    return {'status': 'OPEN_INPUT' if raw_missing else 'PARTIAL', 'remaining': remaining,
            'variants': request['variants'], 'tasks_checked': len(tasks),
            'original_request_sha256': original_request_sha,
            'rebased_request_sha256': canonical_hash(rebased), 'convergence': checked_gates,
            'native_likelihood_replayed': native_replay is not None,
            'replayed_result_sha256': canonical_hash(native_replay) if native_replay else None,
            'cosmological_optimization': 'NOT_PERFORMED', 'confidence_calibrated': False,
            'combination_status': 'SEPARATE_ALTERNATIVES'}
