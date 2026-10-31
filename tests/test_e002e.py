"""Independent identities, solver references and stage/provenance failures."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from scipy import sparse as sp
from scipy.linalg import expm
from e002_exp.model import build_liouvillian, make_direct_rhs, ketbra, maxabs
from e002c_exp.model import build as old_build
from e002d_exp.model import build as d_build, jump_diagonals, damping
from e002e_exp.space import Space, liouvillian
from e002e_exp.model import make_small, make_full, selective_difference, IC_ALPHA
from e002e_exp.numerics import Bordered, state_checks, values, ratio
from e002e_exp.observations import frequency_response, propagate_qrt, schur_response, g0, qrt_inputs
from e002e_exp.analysis import renewal_check, symmetry_check, evaluate_predictions
from e002e_exp.export import conditional_values, validate_conditionals, serial, real_values, save_case, write_manifest, verify_report
from e002e_exp.plan import inventory, selected_work, workload, validate_predictions, ROOT
from e002e_exp.runtime import runtime_gate, compare_environment


def small_case(d=4, mask=6, epsilon=.17, phi=.5, v=1., source=.5):
    return dict(dimension=d, mask=mask, epsilon=epsilon, phi_over_pi=phi, v_over_J=v, source=source,
                sink=.5, node_noise=.05, jump_convention='three_sqrt_phi_Z')


def full_case(model='QS', epsilon=.17, phi=.5, v=1.):
    return dict(model=model, epsilon=epsilon, phi_over_pi=phi, node_noise=.05, m6_v_over_J=v)


def stationary(model, method='lu'):
    solver = Bordered(model['L'], model['space'], method=method, rtol=1e-12, atol=1e-14)
    state, _ = solver.solve(trace=1.)
    return state, solver


class ReducedAlgebra(unittest.TestCase):
    def test_indices_and_complex_observable(self):
        space = Space(np.array([(k//27).bit_count() for k in range(216)]))
        self.assertEqual([len(g) for g in space.groups], [27, 81, 81, 27])
        self.assertEqual(space.size, 14580)
        rng = np.random.default_rng(842); x = rng.normal(size=space.size)+1j*rng.normal(size=space.size)
        self.assertTrue(np.array_equal(space.pack(space.unpack(x)), x))
        self.assertAlmostEqual(abs(space.trace(x)-np.trace(space.unpack(x))), 0., places=12)
        a = np.zeros((216, 216), complex); a[54, 108] = 1j; a[108, 54] = 2.
        self.assertAlmostEqual(abs(space.row(a)@x-np.trace(a@space.unpack(x))), 0., places=12)

    def test_small_generators_against_full_kron_all_columns(self):
        for d, mask, v in ((4, 6, 0.), (4, 7, .5), (8, 6, 0.), (8, 7, .5)):
            model = make_small(small_case(d, mask, v=v)); s = model['space']
            full = build_liouvillian(model['H'], model['jumps'])
            self.assertLess(maxabs(model['L']-full[s.indices][:, s.indices]), 1e-13)

    def test_charge_violating_jump_rejected(self):
        with self.assertRaises(ValueError):
            liouvillian(sp.csr_matrix((2, 2)), [('x', ketbra(2, 0, 1)+ketbra(2, 1, 0))], Space([0, 1]))

    def test_source_transfers_two_sector_coherences(self):
        s = Space([k.bit_count() for k in range(8)])
        C = sp.kron(ketbra(2, 1, 0), sp.eye(4), format='csr')
        L = liouvillian(sp.csr_matrix((8, 8)), [('source', C)], s)
        a = np.zeros((8, 8), complex); a[1, 2] = .7+.2j
        out = s.unpack(L@s.pack(a))
        self.assertAlmostEqual(abs(out[5, 6]-(.7+.2j)), 0.)
        self.assertAlmostEqual(abs(out[1, 2]+(.7+.2j)), 0.)


class NumericalReferences(unittest.TestCase):
    def test_thermal_stationary_and_response(self):
        s = Space([0, 1]); up = ketbra(2, 1, 0); down = up.getH()
        L = liouvillian(sp.csr_matrix((2, 2)), [('up', up), ('down', np.sqrt(2.)*down)], s)
        solver = Bordered(L, s); x, _ = solver.solve(trace=1.)
        np.testing.assert_allclose(x, [2/3, 1/3], atol=1e-14)
        derivative, _ = solver.solve(np.array([2/3, -2/3]))
        np.testing.assert_allclose(derivative, [-2/9, 2/9], atol=1e-14)
        self.assertTrue(state_checks(L, s, x)['pass'])

    def test_small_ness_independent_exponential_and_solver(self):
        model = make_small(small_case(4, 7)); x, _ = stationary(model); y, _ = stationary(model, 'gmres_ilu')
        empty = np.zeros(model['space'].size, complex); empty[0] = 1.
        reference = expm(model['L'].toarray()*250.)@empty
        np.testing.assert_allclose(x, reference, atol=2e-10)
        np.testing.assert_allclose(x, y, atol=1e-11)

    def test_zero_link_branch_and_nonunique_unrestricted(self):
        for d in (4, 8):
            model = make_small(small_case(d, 6, v=0.)); state, _ = stationary(model)
            self.assertIn('n1_zero', model['branch'])
            self.assertLess(abs(values(model, state)['F'].imag), 1e-12)
            self.assertLess(maxabs(model['n'][1]), 1e-15)
        with self.assertRaises(RuntimeError):
            Bordered(sp.csr_matrix((2, 2)), Space([0, 1]))

    def test_gauge_noise_and_renewal(self):
        records = []
        for phi in (0., .5):
            model = make_small(small_case(4, 6, phi=phi)); state, _ = stationary(model)
            records.append(values(model, state)['F'])
            self.assertEqual(renewal_check(model, state)['status'], 'PASS')
        self.assertAlmostEqual(abs(records[0]-records[1]), 0., places=12)
        conditional = []
        for pump in (.05, .5):
            model = make_small(small_case(4, 7, source=pump)); x, _ = stationary(model); vals = values(model, x)
            conditional.append(vals['F']/vals['p_e'])
            self.assertEqual(renewal_check(model, x)['status'], 'PASS')
        self.assertAlmostEqual(abs(conditional[0]-conditional[1]), 0., places=11)

    def test_frequency_against_dense_and_conjugate(self):
        model = make_small(small_case()); state, prepared = stationary(model)
        xp, vp, _, _ = frequency_response(model, state, .7)
        xm, vm, _, _ = frequency_response(model, state, -.7)
        np.testing.assert_allclose(vp['F'], np.conj(vm['F']), atol=1e-12)
        from e002e_exp.observations import source_input
        reference = np.linalg.solve(.7j*np.eye(model['space'].size)-model['L'].toarray(), source_input(model, state))
        np.testing.assert_allclose(xp, reference, atol=1e-12)
        x0, _, _, _ = frequency_response(model, state, 0., prepared)
        self.assertLess(maxabs(model['L']@x0+source_input(model, state)), 1e-11)

    def test_qrt_against_matrix_exponential(self):
        model = make_small(small_case()); x, _ = stationary(model); names = ('J_h', 'p_e', 'K')
        result = propagate_qrt(model, x, .2, .002, .02, names)
        inputs, var = qrt_inputs(model, x, names); rows = np.vstack([model['space'].row(model['observables'][n]) for n in names])
        expected = np.array([rows@expm(model['L'].toarray()*t)@inputs for t in result['times']])
        np.testing.assert_allclose(result['C'], expected, atol=2e-11)
        self.assertEqual(result['summary']['tail_status'], 'TAIL_UNRESOLVED')
        self.assertFalse(result['summary']['positivity_test_applied'])

    def test_schur_matches_direct_with_complex_input_output(self):
        rng = np.random.default_rng(11); a = rng.normal(size=(7, 7))+1j*rng.normal(size=(7, 7)); L = a-10*np.eye(7)
        b = rng.normal(size=7)+1j*rng.normal(size=7); row = rng.normal(size=7)+1j*rng.normal(size=7)
        s = schur_response(sp.csr_matrix(L), b, row, [1, 3, 4], .7j, rtol=1e-12)
        np.testing.assert_allclose(s['x'], np.linalg.solve(.7j*np.eye(7)-L, b), atol=1e-11)
        self.assertLess(s['reconstruction_error'], 1e-12)
        self.assertAlmostEqual(abs(s['total'])**2, abs(s['background'])**2+abs(s['mediated'])**2+s['cross_intensity'], places=12)
        with self.assertRaises(ValueError):
            schur_response(sp.csr_matrix(L), b, row, [1], 0.)

    def test_g0_against_scattering_inverse(self):
        for eps in (-.5, -.125, 0., .125, .5):
            for v in (.5, 1.):
                H = np.array([[0., 0., 1.], [0., eps, v], [1., v, 0.]])
                G = np.linalg.inv(-H+.5j*np.diag([.5, 0., .5]))
                self.assertAlmostEqual(.25*abs(G[2, 0])**2, g0(eps, v)['intensity'], places=12)


class FullOperators(unittest.TestCase):
    def test_pinned_builder_and_reduction(self):
        rng = np.random.default_rng(349)
        for variant in ('QS', 'RR_QS', 'IC1_QS'):
            c = full_case(variant); m = make_full(c)
            old = old_build(dict(model=variant, phi_over_pi=.5, detuning=.17, dephasing=.05), IC_ALPHA if variant == 'IC1_QS' else None)
            self.assertLess(maxabs(m['H']-old['H']), 1e-12)
            s = m['space']; self.assertLess(maxabs(m['L']-old['L'][s.indices][:, s.indices]), 1e-12)
            direct = make_direct_rhs(m['H'], m['jumps'])
            for _ in range(2):
                v = rng.normal(size=s.size)+1j*rng.normal(size=s.size)
                expected = s.pack(direct(s.unpack(v).ravel(order='F')).reshape(216, 216, order='F'), tolerance=1e-10)
                self.assertLess(maxabs(expected-m['L']@v), 5e-12)
            self.assertTrue(symmetry_check(m)['symmetry_applicable'])

    def test_mask_deformation_independent_and_cross_coherence(self):
        from e002c_exp.model import operators
        o = operators(); base = make_full(full_case(), assemble=False); changed = make_full(full_case(v=.5), assemble=False)
        support = sp.diags(np.tile((o['mask_id'] == 6).astype(float), 8))
        up = o['up']; hop = up[1]@up[2].getH()+up[2]@up[1].getH()
        expected = -.5*support@hop
        self.assertLess(maxabs(changed['H']-base['H']-expected), 1e-12)
        self.assertLess(maxabs(changed['currents'][1]-(sp.eye(216)-.5*support)@base['currents'][1]), 1e-12)
        rho = np.zeros((216, 216), complex); rho[2*27+8, 4*27+26] = .5
        rho += rho.conj().T
        self.assertGreater(maxabs(expected@rho-rho@expected), .1)
        self.assertTrue(symmetry_check(changed)['symmetry_applicable'])

    def test_selective_derivative_against_original_channels(self):
        s = Space([(k//27).bit_count() for k in range(216)])
        for name in ('S2a', 'S1b', 'M1', 'M2'):
            old = -damping(jump_diagonals(name, 'T', 1.))+damping(jump_diagonals(name, 'C', 1.))
            np.testing.assert_allclose(selective_difference(s, name).diagonal(), old.ravel(order='F')[s.indices], atol=1e-15)


class WorkflowGuards(unittest.TestCase):
    def test_inventory_and_stages(self):
        g, b, f = [selected_work(x) for x in ('G', 'baseline', 'F2')]
        self.assertEqual(len(g['small']), 92); self.assertEqual(len(b['full']), 24); self.assertEqual(len(f['full']), 20)
        self.assertEqual(sum(len(x['tasks']) for x in b['full'])+20+len(b['frequency']), 94)
        self.assertEqual(workload(b)['correlation_inputs'], 18)
        self.assertTrue(all(x['m6_v_over_J'] == 1 for x in b['full']))

    def test_template_and_missing_predictions_rejected(self):
        template = json.loads((ROOT/'experiments/e002e/f2_prereg_predictions.template.json').read_text())
        with self.assertRaises(ValueError):
            validate_predictions(template, 'a'*40)
        template.update(status='FROZEN', code_commit='a'*40, created_at_utc='2026-10-31T00:00:00Z', frozen_at_utc='2026-10-31T00:00:01Z')
        with self.assertRaises(ValueError):
            validate_predictions(template, 'a'*40)

    def test_null_and_uncertainty_reconstruction(self):
        self.assertIsNone(ratio(1., 1e-7)['value'])
        self.assertIsNone(ratio(1., 1.1e-6, 1e-9, 2e-7)['value'])
        raw = dict(h6=.1, P_m6_N2=.2); err = dict(h6=1e-8, P_m6_N2=2e-8)
        c = conditional_values(raw, err); validate_conditionals(raw, c, err)
        c['j6']['value'] += 1e-4
        with self.assertRaises(ValueError):
            validate_conditionals(raw, c, err)

    def test_runtime_does_not_accept_unknown_calibration_or_short_work(self):
        f = dict(expected_seconds=1., lower_seconds=.8, upper_seconds=1.3)
        self.assertEqual(runtime_gate(f, 1., {'n': 2}, {'n': 2}, True, False)['status'], 'NOT_EVALUABLE')
        self.assertEqual(runtime_gate(f, 1., {'n': 2}, {'n': 1}, True, True)['status'], 'REVIEW_REQUIRED')
        self.assertEqual(runtime_gate(f, .1, {'n': 2}, {'n': 2}, True, True)['status'], 'REVIEW_REQUIRED')
        self.assertFalse(compare_environment({}, {})['comparable'])

    def test_report_tamper_detected(self):
        m = make_small(small_case()); state, _ = stationary(m); raw = real_values(values(m, state))
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp)/'report'; report.mkdir(); full = Path(temp)/'full'; full.mkdir()
            rec = dict(id='small_000', case=m['case'], raw=raw, conditional=conditional_values(raw), quality={'pass': True})
            save_case(report, full, rec, state, m['space']); write_manifest(report); verify_report(report)
            p = report/'small_000.json'; p.write_text(p.read_text()+' ')
            with self.assertRaises(ValueError):
                verify_report(report)


if __name__ == '__main__':
    unittest.main()
