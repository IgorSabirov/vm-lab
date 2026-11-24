"""Manufactured P9 bundles test identity and audit policy, not cosmological fits."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, canonical_hash, read_json, sha256, write_json
from r135.external_cmb import SPT
from r135.external_cmb_audit import audit_external_cmb, ADAPTER, CORNERS, ENGINES

SOFTWARE = Path(__file__).resolve().parents[1]


def fixture(root, *, refined=False):
    source = read_json(SOFTWARE/'external_cmb_reference/native_control/fixed.json')
    levels = [{'tol_perturbations_integration': 1e-5}, {'tol_perturbations_integration': 1e-6}] if refined else [{}]
    config = {'external_cmb': {'variants': [SPT], 'cache': '/unavailable/original/cache',
                              'spt_tau_prior': 'include', 'offline': True}}
    if refined:
        config.update(class_refinement=levels, max_cmb_delta_logL=.1)
    request = {**config['external_cmb'], 'adapter_sha256': sha256(ADAPTER), 'mode': 'conditional', 'spectra': {}}
    result = {'schema': 'R135-external-CMB-evaluations-v1', 'evaluations': {},
              'receipt': {SPT: source['receipt'][SPT]},
              'combination': {'status': 'SEPARATE_ALTERNATIVES', 'joint_logL': None},
              'cosmological_optimization': 'NOT_PERFORMED', 'confidence_calibrated': False}
    result['receipt'][SPT]['actual_evaluations'] = len(ENGINES)*len(CORNERS)*len(levels)
    gates = {}
    ell = np.arange(2, 4096)
    raw = np.column_stack([ell, np.ones(len(ell))*3, np.ones(len(ell))*2,
                           np.ones(len(ell))*.1, -np.ones(len(ell))])
    factor = 2*np.pi/(ell*(ell + 1))
    spectra = {'ell': ell.tolist(), 'unit': 'microK^2', 'convention': 'Cl', 'lensed': True,
               **{name: (raw[:, i]*factor).tolist() for i, name in enumerate(('TT', 'EE', 'BB', 'TE'), 1)}}
    for engine in ENGINES:
        for corner in CORNERS:
            key = f'{engine}/{corner}'
            logs = []
            for index, precision in enumerate(levels):
                final = index == len(levels) - 1
                tag = key if final else key+f'@accuracy{index}'
                directory = root/'class'/engine/(corner if final else corner+f'.accuracy-{index}')
                directory.mkdir(parents=True)
                write_json(directory/'spectra.json', spectra)
                np.savetxt(directory/'spectra_00_cl_lensed.dat', raw)
                ini = 'tau_reio = 0.054\nlensing = yes\nformat = camb\nl_max_scalars = 4095\nYHe = 0.245\n'
                ini += ''.join(f'{k} = {v}\n' for k, v in precision.items())
                (directory/'parameters.ini').write_text(ini)
                proof = {'spectra_sha256': sha256(directory/'spectra.json'),
                         'input': {'parameters': {'tau_reio': .054}, 'precision': precision, 'l_max_scalars': 4095},
                         'parameters_sha256': sha256(directory/'parameters.ini'),
                         'files': {p.name: sha256(p) for p in directory.iterdir()}}
                write_json(directory/'receipt.json', proof)
                task = {'path': '/relocated/from/another/machine/'+tag+'/spectra.json',
                        'sha256': sha256(directory/'spectra.json'), 'cosmology': {'tau_reio': .054},
                        'producer_receipt': {'path': '/relocated/from/another/machine/'+tag+'/receipt.json',
                                             'sha256': sha256(directory/'receipt.json')}}
                request['spectra'][tag] = task
                record = deepcopy(source['evaluations']['baseline'][SPT])
                record.update(logL=-100. + index*.01, log_prior=-.125, log_posterior=-100.125 + index*.01,
                              consumed_file_sha256=task['sha256'], producer_receipt=task['producer_receipt'],
                              spectra_sha256=canonical_hash(spectra), cosmology_sha256=canonical_hash(task['cosmology']))
                result['evaluations'][tag] = {SPT: record}
                logs.append(record['log_posterior'])
            if refined:
                gates[key+'/'+SPT] = {'status': 'PASS', 'logL_by_accuracy': logs,
                                     'adjacent_delta_logL': np.abs(np.diff(logs)).tolist(), 'max_delta_logL': .1}
    result['request_sha256'] = canonical_hash(request)
    write_json(root/'external_cmb_request.json', request)
    write_json(root/'external_cmb_evaluations.json', result)
    write_json(root/'external_cmb_convergence.json', gates or {'status': 'NOT_VALIDATED'})
    return config, request, result


def save(root, request, result):
    result['request_sha256'] = canonical_hash(request)
    write_json(root/'external_cmb_request.json', request)
    write_json(root/'external_cmb_evaluations.json', result)


class ExternalCMBAuditTests(unittest.TestCase):
    def test_requested_missing_evidence_is_open(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(audit_external_cmb(root, {})['status'], 'NOT_REQUESTED')
            result = audit_external_cmb(root, {'external_cmb': {'variants': [SPT]}})
            self.assertEqual(result['status'], 'OPEN_INPUT')
            self.assertEqual(len(result['remaining']), 3)

    def test_relocated_bundle_checks_local_raw_spectrum_but_keeps_cosmology_open(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);config, request, result = fixture(root)
            report = audit_external_cmb(root, config)
            self.assertEqual(report['status'], 'PARTIAL')
            self.assertEqual(report['tasks_checked'], 10)
            self.assertNotEqual(report['original_request_sha256'], report['rebased_request_sha256'])
            self.assertFalse(report['native_likelihood_replayed'])
            self.assertIn('EXTERNAL_CMB_COMMON_COSMOLOGY_OPTIMIZATION_NOT_PERFORMED', report['remaining'])
            path = root/'class/linx/00/spectra_00_cl_lensed.dat'
            path.write_text('tampered native output')
            with self.assertRaisesRegex(InputError, 'original CLASS output'):
                audit_external_cmb(root, config)

    def test_prior_tau_and_missing_point_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);config, request, result = fixture(root)
            modified = deepcopy(result)
            modified['evaluations']['linx/00'][SPT]['priors']['tau']['value'] = .051
            write_json(root/'external_cmb_evaluations.json', modified)
            with self.assertRaisesRegex(InputError, 'prior vector'):
                audit_external_cmb(root, config)
            modified = deepcopy(result)
            modified['evaluations']['linx/00'][SPT]['log_prior'] = 0.
            modified['evaluations']['linx/00'][SPT]['log_posterior'] += .125
            write_json(root/'external_cmb_evaluations.json', modified)
            with self.assertRaisesRegex(InputError, 'prior arithmetic'):
                audit_external_cmb(root, config)
            request['spectra']['linx/../../hijack'] = request['spectra'].pop('linx/00')
            result['evaluations']['linx/../../hijack'] = result['evaluations'].pop('linx/00')
            save(root, request, result)
            with self.assertRaisesRegex(InputError, 'engine/corner/accuracy'):
                audit_external_cmb(root, config)

    def test_original_request_hash_is_checked_before_relocation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);config, request, result = fixture(root)
            request['spectra']['linx/00']['path'] = '/a/different/original/path'
            write_json(root/'external_cmb_request.json', request)
            with self.assertRaisesRegex(InputError, 'original request'):
                audit_external_cmb(root, config)

    def test_refinement_is_reconstructed_and_must_use_same_physics(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);config, request, result = fixture(root, refined=True)
            report = audit_external_cmb(root, config)
            self.assertEqual(len(report['convergence']), 10)
            self.assertEqual(report['tasks_checked'], 20)
            self.assertNotIn('EXTERNAL_CMB_CLASS_REFINEMENT_NOT_PERFORMED', report['remaining'])
            gates = read_json(root/'external_cmb_convergence.json')
            gates['linx/00/'+SPT]['adjacent_delta_logL'] = [0.]
            write_json(root/'external_cmb_convergence.json', gates)
            with self.assertRaisesRegex(InputError, 'convergence gate'):
                audit_external_cmb(root, config)

    def test_fresh_worker_receives_rebound_files_and_all_registered_points(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)/'bundle';root.mkdir();config, request, result = fixture(root)
            cache = Path(td)/'cache';cache.mkdir()
            for s in result['receipt'][SPT]['data_sources'].values():
                (cache/s['sha256']).touch()
            def worker(actual, python, output, *, interpreter_sha256):
                self.assertFalse(any(output.iterdir()))
                self.assertEqual(set(actual['spectra']), set(request['spectra']))
                self.assertTrue(all(Path(t['path']).is_relative_to(root) for t in actual['spectra'].values()))
                self.assertTrue(all(Path(t['producer_receipt']['path']).is_file() for t in actual['spectra'].values()))
                self.assertEqual(actual['cache'], str(cache))
                return deepcopy(result)
            replay = {'external_cmb': {'python': sys.executable, 'python_sha256': sha256(Path(sys.executable)),
                                       'cache': str(cache)}}
            with patch('r135.external_cmb_audit.isolated_batch', side_effect=worker) as call:
                report = audit_external_cmb(root, config, replay, Path(td)/'audit')
            self.assertEqual(call.call_count, 1)
            self.assertTrue(report['native_likelihood_replayed'])
            self.assertEqual(report['status'], 'PARTIAL')


if __name__ == '__main__':
    unittest.main()
