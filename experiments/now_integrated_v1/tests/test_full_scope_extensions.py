import unittest
from nowexp.state import Config
from nowexp.engine import Engine
from nowexp.enumeration import FiniteEnumeration
from nowexp.typed_reactions import exhaustive_v1_control,reaction
from nowexp.joint_preparation import instrument_distribution
from nowexp.readout_analysis import reconstruction


class FullScopeExtensions(unittest.TestCase):
    def cfg(self,**changes):
        base=dict(separate_apparatus=True,inherited_routes=True,forced_content=(1,1),donor_precursor=30)
        base.update(changes);return Config(**base)

    def test_writer_reader_are_material_and_work_after_seed_retirement(self):
        e=Engine(self.cfg(),0);r=e.run()
        self.assertTrue(r['all_functional'])
        self.assertEqual(r['material_and_credit_balance'],r['initial_totals'])
        self.assertEqual(set(r['profile'][1]['apparatus_types']),{'writer','reader'})
        self.assertTrue(r['profile'][1]['contact_endpoints'])

    def test_no_transmitted_template_stops_child_without_global_fallback(self):
        r=Engine(self.cfg(transmit_route=False),0).run()
        self.assertTrue(r['parent_function']);self.assertFalse(r['child_function'])
        self.assertEqual(r['profile'][1]['route_template'],[])

    def test_fragment_missing_duplicate_and_capacity_controls(self):
        good=Engine(self.cfg(fragmented_records=True),0).run()
        repeat=Engine(self.cfg(fragmented_records=True,duplicate_fragment=True),0).run()
        lost=Engine(self.cfg(fragmented_records=True,drop_fragment=True),0).run()
        tiny=Engine(self.cfg(fragmented_records=True,fragment_slots=0),0).run()
        self.assertTrue(good['all_functional']);self.assertTrue(repeat['all_functional'])
        self.assertFalse(lost['parent_function']);self.assertFalse(tiny['parent_function'])

    def test_branching_does_not_duplicate_donor_or_apparatus(self):
        e=Engine(self.cfg(branching=True,donor_fuel=64),0);r=e.run()
        self.assertEqual(r['material_and_credit_balance'],r['initial_totals'])
        self.assertEqual(set(r['profile'][0]['transmitted_to']),{'N1','N2'})
        ids=[a['identity'] for c in e.cells.values() for a in c.apparatus]
        self.assertEqual(len(ids),len(set(ids)))

    def test_v1_support_and_v2_functional_access(self):
        self.assertTrue(exhaustive_v1_control()['all_same_support'])
        self.assertEqual(reaction(1,{1:1},'V2',1)['added_type'],2)
        base=dict(seed_writer=False,prepared_records=True)
        one=Engine(self.cfg(**base,production_semantics='V1'),0).run()
        two=Engine(self.cfg(**base,production_semantics='V2'),0).run()
        self.assertFalse(one['child_function']);self.assertTrue(two['child_function'])

    def test_equal_quantum_marginals_different_joint_readout(self):
        a=instrument_distribution('bell_x');b=instrument_distribution('dephased_x')
        self.assertEqual(a['marginal_a'],b['marginal_a'])
        self.assertEqual(a['marginal_b'],b['marginal_b'])
        qa={tuple(x['bits']):x['probability'] for x in a['outcomes']}
        qb={tuple(x['bits']):x['probability'] for x in b['outcomes']}
        self.assertAlmostEqual(qa[(1,1)],.5);self.assertAlmostEqual(qb[(1,1)],.25)

    def test_A_uses_current_state_without_external_access(self):
        first=reaction(1,{1:1},'A',1)
        second=reaction(first['state_type'],first['access'],'A',first['state_type'])
        self.assertIsNotNone(second)
        e=Engine(self.cfg(seed_writer=False,prepared_records=True,production_semantics='A'),0)
        r=e.run()
        self.assertEqual(r['initial_totals'],r['material_and_credit_balance'])

    def test_incomplete_fragments_expire_without_decoding(self):
        e=Engine(self.cfg(fragmented_records=True,drop_fragment=True),0);e.run()
        self.assertEqual(e.cells['N0'].fragments,{})
        self.assertFalse(e.cells['N0'].decoded)

    def test_imported_contact_keeps_delivered_address(self):
        e=Engine(self.cfg(imported_contacts=True),0);r=e.run()
        self.assertIn('N1',r['profile'][0]['transmitted_to'])

    def test_repeat_and_transport_balance(self):
        for delta in (dict(repair_rounds=2,donor_fuel=160,donor_precursor=80),
                      dict(transport_support=True,damage_transport=True,read_wait=64,donor_fuel=100,donor_precursor=60)):
            r=Engine(self.cfg(**delta),0).run()
            self.assertEqual(r['initial_totals'],r['material_and_credit_balance'])
            self.assertTrue(r['finished'])

    def test_completion_trace_is_not_interaction_shutdown(self):
        for mode in ('erase','trace','isolate','transfer','decay'):
            e=Engine(self.cfg(completion_mode=mode),0);e.run()
            self.assertTrue(all(x['interaction_stopped']==(mode!='trace') for x in e.completion_events))
            if mode in ('erase','transfer','decay'):
                self.assertEqual([x['bit'] for x in e.environment_records if x.get('mode')=='classical_completion'],[1,1])

    def test_readout_matrix_is_a_declared_operator(self):
        report=reconstruction(Config())
        self.assertEqual(len(report['matrix']),3)
        self.assertAlmostEqual(report['sigma_min'],1)
        self.assertTrue(report['robust'])


if __name__=='__main__':unittest.main()
