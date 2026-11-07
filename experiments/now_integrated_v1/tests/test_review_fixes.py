import copy
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from nowexp.engine import Engine
from nowexp.enumeration import FiniteEnumeration, input_distribution
from nowexp.state import Config
from nowexp.provenance import atomic_json, configure_io_budget, gate, digest
from nowexp.observables import summarize, ancestor_report, paired_contrasts, metric_range
from nowexp.memory import write, outcomes, unpack
from nowexp.runner import make_tasks

ROOT = Path(__file__).parents[1]


def enumerated(cfg):
    job = FiniteEnumeration(cfg)
    while job.pending:
        job.advance()
    return dict(case_id='test', config=asdict(cfg), seed=0,
                sampling_mode='finite_enumeration', **job.result())


class ReviewFixes(unittest.TestCase):
    def test_all_deterministic_cases_are_seed_invariant(self):
        cases=json.loads((ROOT/'preregistration/CASES.json').read_text())['cases']
        for case in cases:
            if case['sampling_mode']=='deterministic':
                cfg=Config(**case['config'])
                with self.subTest(case=case['id']):
                    self.assertEqual(Engine(cfg,0).run(),Engine(cfg,17).run())

    def test_threshold_is_taken_from_protocol(self):
        cfg=Config(forced_content=[1,1])
        cfg.thresholds['function_health_at_least']=10
        self.assertFalse(Engine(cfg,0).run()['parent_function'])
        cfg=Config(forced_content=[0,1])
        cfg.thresholds['required_decoded_content']=[0,1]
        self.assertTrue(Engine(cfg,0).run()['all_functional'])

    def test_different_addresses_have_different_roles(self):
        a=Engine(Config(forced_content=[1,1],contact_address_enabled=False),0).run()
        b=Engine(Config(forced_content=[1,1],successor_address_enabled=False),0).run()
        self.assertFalse(a['parent_function'])
        self.assertTrue(b['parent_function'])
        self.assertFalse(b['child_function'])

    def test_new_apparatus_must_have_working_interfaces(self):
        for changes in ({'produced_template':0},{'produced_disabled_roles':['read']},
                        {'produced_disabled_roles':['write']},{'produced_disabled_roles':['repair']}):
            result=Engine(Config(forced_content=[1,1],**changes),0).run()
            self.assertFalse(result['child_function'])

    def test_inbox_record_decode_are_separate_caps(self):
        for change in ({'inbox_slots':0},{'record_slots':1},{'working_slots':1}):
            e=Engine(Config(forced_content=[1,1],**change),0)
            self.assertFalse(e.run()['parent_function'])
            e.audit()
        e=Engine(Config(forced_content=[1,1],initial_seed=False,inbox_lifetime=1),0)
        r=e.run()
        self.assertEqual(r['profile'][0]['pending_records'],0)
        self.assertTrue(any(x.startswith('inbox_expired') for x in r['profile'][0]['failures']))

    def test_every_carrier_respects_its_own_speed(self):
        e=Engine(Config(forced_content=[1,1],receiver_velocity=.2),0)
        e.run()
        for channel in (x for x in e.log if x['kind']=='channel'):
            self.assertLessEqual(abs(channel['x1']-channel['x0']),
                channel['speed']*(channel['received']-channel['sent'])+1e-10)

    def test_causal_graph_links_write_read_production(self):
        e=Engine(Config(forced_content=[1,1]),0)
        e.run()
        events={x['event']['id']:x['event'] for x in e.log if x['kind']=='event'}
        instruments={x['id']:x for x in e.log if x['kind']=='instrument'}
        nodes=dict(events,**instruments)
        for node in nodes.values():
            self.assertTrue(set(node['parents']) <= nodes.keys())
        self.assertIn('N0:read',events['N0:produce']['parents'])
        self.assertTrue(any(':write:' in p for p in events['N0:read']['parents']))
        visiting,visited=set(),set()
        def visit(identity):
            self.assertNotIn(identity,visiting)
            if identity in visited:return
            visiting.add(identity)
            for parent in nodes[identity]['parents']:visit(parent)
            visiting.remove(identity);visited.add(identity)
        for identity in nodes:visit(identity)

    def test_exact_classical_probability_and_conditional_transmission(self):
        row=enumerated(Config())
        report=summarize([row])['test']
        self.assertEqual(report['q_final'],5/16)
        self.assertEqual(report['per_generation'][0]['p_transfer_given_function'],1)
        self.assertIsNone(report['per_generation'][-1]['p_transfer_given_function'])
        self.assertAlmostEqual(sum(report['joint_profile'].values()),1)
        self.assertEqual(len(row['outcomes']),4)

    def test_exact_born_tree_and_branch_resume(self):
        cfg=Config(forced_content=[1,1],memory='finite_static',bath_modes=4,generations=2)
        job=FiniteEnumeration(cfg)
        job.advance()
        restored=FiniteEnumeration(cfg,json.loads(json.dumps(job.snapshot())))
        while job.pending:job.advance()
        while restored.pending:restored.advance()
        self.assertEqual(job.result(),restored.result())
        self.assertAlmostEqual(job.result()['probability_mass'],1,places=12)
        self.assertGreater(len(job.leaves),1)

    def test_numerical_memory_grid_and_post_states(self):
        for modes in (4,8,16,32):
            for detuning in (0,.02,.07,.15):
                data=write(1,'finite_dark',0,modes,.35,detuning)
                for t in (16,32,64):
                    options=outcomes(data,t)
                    self.assertAlmostEqual(sum(p for _,p,_,_ in options),1,places=10)
                    for _,p,q,post in options:
                        self.assertGreater(p,0)
                        self.assertLess(q['probability_correction_l1'],1e-9)
                        rho=unpack(post['rho'])
                        self.assertLess(abs(np.trace(rho)-1),1e-9)
                        self.assertGreaterEqual(np.linalg.eigvalsh(rho).min(),-1e-9)

    def test_inconclusive_lineage_uses_unresolved_return(self):
        contract={k:k for k in ('id','ancestor','before','promised_delta','prediction','evidence_refs',
                  'positive_return','negative_return','unresolved_return','relation')}
        contract['evaluation']=dict(kind='contrast',id='x',lower=.95,upper=1)
        value=dict(status='EXECUTED_DESCRIPTIVE',mean=1,nominal_bounded_95_halfwidth=.5)
        report=ancestor_report([contract],[],{}, {'x':value})[0]
        self.assertEqual(report['status'],'INCONCLUSIVE')
        self.assertEqual(report['realized_return'],'unresolved_return')

    def test_stochastic_health_bound_has_range_factor(self):
        self.assertEqual(metric_range('mean_health',[]),10)

    def test_gate_blocks_missing_and_wrong_acceptance(self):
        with self.assertRaises(ValueError):gate(ROOT,'smoke','s','c')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'accept.json'
            atomic_json(p,dict(status='accepted',source_digest='s',review_reference='review',
                user_decision_reference='current user instruction',authorized_phases=['smoke']))
            self.assertEqual(gate(ROOT,'smoke','s','c',p)['stage'],'REVIEWED_SMOKE')
            with self.assertRaises(ValueError):gate(ROOT,'smoke','changed','c',p)
            with self.assertRaises(ValueError):gate(ROOT,'main','s','c',p)
            with self.assertRaises(ValueError):gate(ROOT,'calibrate','s','c',p)

    def test_prospective_disk_guard_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'snapshot.json'
            atomic_json(p,{'old':True})
            configure_io_budget(d,100)
            try:
                with self.assertRaises(RuntimeError):atomic_json(p,{'huge':'x'*1000})
                self.assertEqual(json.loads(p.read_text()),{'old':True})
            finally:
                import nowexp.provenance as provenance
                provenance.IO_BUDGET=None

    def test_main_workload_and_all_contrast_branches_exist(self):
        plan=json.loads((ROOT/'preregistration/PROTOCOL.json').read_text())
        cases=json.loads((ROOT/'preregistration/CASES.json').read_text())
        selected,tasks=make_tasks(plan,cases,'main')
        self.assertEqual(len(tasks),plan['proposed_main_tasks'])
        names={case['id'] for case in selected}
        for contrast in cases['contrasts']:
            self.assertTrue(set(contrast['cases'])<=names)
        _, calibration=make_tasks(plan,cases,'calibrate')
        quantum_exact=[t for t in calibration if t['config']['memory']!='classical' and t['sampling_mode']=='finite_enumeration']
        self.assertTrue(quantum_exact)
        self.assertTrue(any(t['case_id'].startswith('mc::') for t in calibration))
