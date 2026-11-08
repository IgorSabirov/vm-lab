"""Review tests; author execution is deferred until technical review."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from nowexp.carrier import Carrier, full_step, fixture
from nowexp.engine import Engine, canonical_hash
from nowexp.enumeration import FiniteEnumeration, input_distribution
from nowexp.state import Config
from nowexp.runner import make_tasks, validate_workload, workload_inventory


ROOT = Path(__file__).resolve().parents[1]


def config(**kwargs):
    values = dict(separate_apparatus=True, inherited_routes=True, task_probe=True,
                  donor_fuel=144, donor_precursor=96, forced_content=(1, 1), max_events=12000)
    values.update(kwargs)
    return Config(**values)


class PatchContracts(unittest.TestCase):
    def test_original_cases_and_contrasts_preserved(self):
        cases = json.loads((ROOT/'preregistration/CASES.json').read_text())
        amendment = json.loads((ROOT/'preregistration/FOUR_CANDIDATE_AMENDMENT.json').read_text())
        old = cases['cases'][:123]
        h = hashlib.sha256(json.dumps(old, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(h, amendment['legacy_cases_sha256'])
        self.assertEqual(len(cases['cases']), 123+len(amendment['new_cases']))
        self.assertEqual(len(cases['contrasts']), 84+len(amendment['new_contrasts']))

    def test_workload_uses_same_runner(self):
        plan = json.loads((ROOT/'preregistration/PROTOCOL.json').read_text())
        cases = json.loads((ROOT/'preregistration/CASES.json').read_text())
        selected, tasks = make_tasks(plan, cases, 'main')
        amendment = json.loads((ROOT/'preregistration/FOUR_CANDIDATE_AMENDMENT.json').read_text())
        self.assertEqual(len(selected), 123+len(amendment['new_cases']))
        self.assertEqual(len(tasks), amendment['main_task_count'])
        self.assertEqual(plan['freeze_state'], 'FROZEN_AFTER_USER_DIRECTIVE')

    def test_workload_drift_is_rejected_before_execution(self):
        plan = json.loads((ROOT/'preregistration/PROTOCOL.json').read_text())
        cases = json.loads((ROOT/'preregistration/CASES.json').read_text())
        amendment = json.loads((ROOT/'preregistration/FOUR_CANDIDATE_AMENDMENT.json').read_text())
        validate_workload(plan, cases, amendment)
        for target in ('main', 'phase', 'amendment'):
            p, a = copy.deepcopy(plan), copy.deepcopy(amendment)
            if target == 'main': p['proposed_main_tasks'] = 326
            elif target == 'phase': p['workload_inventory']['smoke']['tasks'] += 1
            else: a['main_task_count'] = 326
            with self.assertRaises(ValueError): validate_workload(p, cases, a)

    def test_user_waiver_keeps_runtime_gate_mandatory(self):
        plan = json.loads((ROOT/'preregistration/PROTOCOL.json').read_text())
        self.assertEqual(plan['freeze_state'], 'FROZEN_AFTER_USER_DIRECTIVE')
        self.assertTrue(plan['execution_authorization']['technical_audit_waived'])
        self.assertTrue(plan['execution_authorization']['runtime_gate_required'])

    def test_input_mass_not_replaced_by_forced_11(self):
        inputs = input_distribution(config(forced_content=None))
        self.assertEqual({tuple(p) for p, _ in inputs}, {(0, 0), (0, 1), (1, 0), (1, 1)})
        self.assertEqual(sum(w for _, w in inputs), 1)

    def test_full_transport_is_not_bits_only_identity(self):
        w, _ = full_step([1, 0, 2], False)
        w, _ = full_step(w, False)
        self.assertNotEqual(w, [1, 0, 2])
        self.assertEqual(w, [0, 1, 2])

    def test_quiet_blocked_fixture(self):
        w = [0, 0, 11]
        for _ in range(3):
            w, _ = full_step(w)
            self.assertEqual(len(w), 3)
        self.assertEqual(w, [0, 0, 11])

    def test_cycle_seam_merge_conserves_every_bit(self):
        w, mapping = full_step([2, 0, 1])
        self.assertEqual(len(w), 2)
        self.assertEqual(mapping[0], mapping[2])
        self.assertEqual([sum((s >> b) & 1 for s in w) for b in range(4)], [1, 1, 0, 0])

    def test_payload_split_has_one_location(self):
        c = Carrier(dict(kind='add_c2_full', id='split', word=[3], anchors={'a': 0},
                         horizon=8, max_vertices=32), ['a'])
        c.pending['p'] = dict(node=0)
        c.advance(1)
        self.assertEqual(len(c.pending), 1)
        self.assertEqual(c.anchors['a'], c.pending['p']['node'])
        self.assertEqual(c.particles(), [1, 1, 0, 0])

    def test_noncausal_import_rejected(self):
        s = fixture('ising_order', ['a', 'b'], 5)
        s['links'].append(['1:0', '0:0'])
        with self.assertRaises(ValueError):
            Carrier(s, ['a', 'b'])

    def test_routes_use_actual_future_links(self):
        c = Carrier(fixture('cdt_strip', ['a', 'b', 'c'], 12), ['a', 'b', 'c'])
        path = c.path('a', 'c', 0, .5)
        self.assertIsNotNone(path)
        self.assertTrue(all(b in c.next[a] for a, b in zip(path, path[1:])))
        self.assertGreaterEqual(c.events[path[-1]]['t'], 3)

    def test_no_damage_off_can_succeed_without_health_gate(self):
        r = Engine(config(restoration_mode='off', corrector=False), 0).run()
        self.assertEqual(r['mean_task_success'], 1)
        self.assertEqual(r['parent_function'], 0)

    def test_single_bit_flip_changes_xor(self):
        for pair in ((0, 0), (0, 1), (1, 0), (1, 1)):
            a = Engine(config(forced_content=pair), 0).run()
            b = Engine(config(forced_content=pair, task_content_intervention='flip_A'), 0).run()
            self.assertEqual(a['mean_task_success'], 1)
            self.assertEqual(b['mean_task_success'], 0)
            self.assertEqual(a['total_spent_fuel'], b['total_spent_fuel'])

    def test_damage_on_off_sham_and_fixed_reserve(self):
        for role in ('writer', 'reader', 'contact'):
            results = {mode: Engine(config(task_damage=role, restoration_mode=mode), 0).run()
                       for mode in ('on', 'off', 'sham')}
            self.assertEqual(results['on']['mean_task_success'], 1)
            self.assertEqual(results['off']['mean_task_success'], 0)
            self.assertEqual(results['sham']['mean_task_success'], 0)
            for r in results.values():
                self.assertEqual(r['initial_totals'], r['material_and_credit_balance'])
                self.assertTrue(all(t['reserve_fuel'] == 5 and t['reserve_material'] == 5 for t in r['task_results']))

    def test_output_reuses_B_and_preserves_overwrite_record(self):
        e = Engine(config(), 0)
        e.run()
        self.assertTrue(all(t['output_slot'] == 'B' and t['record_slots_after'] == 2 for t in e.result()['task_results']))
        self.assertEqual(len([x for x in e.environment_records if x.get('mode') == 'task_overwrite']), 3)

    def test_snapshot_preserves_inflight_payload_and_task(self):
        for family in ('add_growing', 'ising_order', 'cdt_strip'):
            e = Engine(config(geometry=dict(fixture=family, horizon=512)), 0)
            while not e.carrier.pending:
                e.step()
            saved = json.loads(json.dumps(e.snapshot()))
            fresh = Engine.restore(saved)
            self.assertTrue(fresh.carrier.pending)
            self.assertEqual(canonical_hash(e.run()), canonical_hash(fresh.run()))
            self.assertEqual(canonical_hash(e.snapshot()), canonical_hash(fresh.snapshot()))

    def test_geometry_changes_real_delivery_trace(self):
        a = Engine(config(geometry=dict(fixture='add_growing', interaction=False)), 0)
        b = Engine(config(geometry=dict(fixture='add_growing', interaction=True)), 0)
        a.run(); b.run()
        self.assertNotEqual(a.carrier.trace, b.carrier.trace)
        self.assertTrue(all(row['kind'] != 'channel' for row in b.log))

    def test_no_silent_unsupported_backend_or_horizon(self):
        with self.assertRaises(ValueError):
            Carrier(dict(kind='C3_D', horizon=5), ['a'])
        c = Carrier(dict(fixture='add_quiet', horizon=5), ['a', 'b', 'c'])
        with self.assertRaises(ValueError):
            c.clock(6)

    def test_new_panel_finite_sum_has_no_lost_mass(self):
        job = FiniteEnumeration(config(forced_content=None, geometry=dict(fixture='add_quiet')))
        while job.pending:
            job.advance()
        r = job.result()
        self.assertEqual(r['probability_mass'], 1)
        self.assertEqual(len(r['outcomes']), 4)
        self.assertTrue(all(x['result']['initial_totals'] == x['result']['material_and_credit_balance'] for x in r['outcomes']))


if __name__ == '__main__':
    unittest.main()
