"""Tests supplied for external review. Author has NOT run this suite."""
import copy
from fractions import Fraction as F
import json
import unittest
import numpy as np

from nowexp.engine import Engine
from nowexp.state import Config
from nowexp.randomness import uniform, exact_histories
from nowexp.kinematics import Worldline, reception, rational_boost
from nowexp.memory import write, read, evolved, response, unpack
from nowexp.observables import finite_closure


class IntegratedCandidate(unittest.TestCase):
    def engine(self, **changes):
        return Engine(Config(**dict({"forced_content":[1,1]}, **changes)), 41)

    def test_complete_classical_path(self):
        e = self.engine()
        r = e.run()
        self.assertTrue(r["all_functional"])
        self.assertEqual(r["initial_totals"], r["material_and_credit_balance"])
        self.assertTrue(all(p["own_apparatus"] >= 1 for p in r["profile"]))
        self.assertTrue(all(p["inherited_apparatus"] == 0 for p in r["profile"]))
        self.assertFalse(any(e.source_alive.values()))

    def test_core_negative_controls(self):
        for mutation in ({"production":False}, {"repair_contacts":False},
                         {"reader_enabled":False}, {"initial_seed":False},
                         {"corrector":False}, {"erase_record":True}):
            with self.subTest(mutation=mutation):
                self.assertFalse(self.engine(**mutation).run()["parent_function"])

    def test_carrier_only_is_not_heredity(self):
        r = self.engine(transfer_apparatus=False).run()
        self.assertTrue(r["parent_function"])
        self.assertFalse(r["child_function"])

    def test_content_changes_action(self):
        self.assertFalse(self.engine(forced_content=[1,0]).run()["parent_function"])
        self.assertTrue(self.engine().run()["parent_function"])

    def test_all_initial_controls_have_same_total(self):
        baseline = self.engine().initial_totals
        for change in ({"initial_seed":False}, {"imported_contacts":True},
                       {"production":False}, {"repair_contacts":False}):
            self.assertEqual(self.engine(**change).initial_totals, baseline)

    def test_same_time_scheduler_order(self):
        self.assertEqual(self.engine().run(), self.engine(scheduler_reverse=True).run())

    def test_snapshot_contains_history_resources_and_queue(self):
        e = self.engine(memory="finite_dark")
        e.run(stop_after=8)
        restored = Engine.restore(json.loads(json.dumps(e.snapshot())))
        self.assertEqual(e.run(), restored.run())

    def test_global_log_does_not_control(self):
        a, b = self.engine(), self.engine()
        b.log.append({"researcher_fake_future":"all_success"})
        self.assertEqual(a.run(), b.run())

    def test_injection_is_detected(self):
        e = self.engine()
        e.cells["N0"].fuel += 1
        with self.assertRaises(ArithmeticError):
            e.audit()

    def test_requests_do_not_spend_remote_money_before_arrival(self):
        e = self.engine()
        while e.queue and min(x["t"] for x in e.queue) < 2:
            e.step()
        self.assertEqual(e.donor["fuel"], e.config.donor_fuel)

    def test_late_supply_can_fail_without_creating_resources(self):
        e = self.engine(supply_delay=100)
        r = e.run()
        self.assertFalse(r["parent_function"])
        self.assertEqual(r["initial_totals"],r["material_and_credit_balance"])

    def test_all_deliveries_are_causal(self):
        e = self.engine(receiver_velocity=.2)
        e.run()
        for event in e.log:
            if event["kind"] == "channel":
                self.assertGreaterEqual(event["received"]-event["sent"]+1e-10,
                                        abs(event["x1"]-event["x0"]))

    def test_rational_boost(self):
        t,x=F(7,3),F(2,5)
        a,b=rational_boost(t,x,F(3,5),F(5,4))
        self.assertEqual(a*a-b*b,t*t-x*x)

    def test_working_memory_is_a_real_budget(self):
        self.assertFalse(self.engine(working_slots=1).run()["parent_function"])

    def test_quantum_dark_and_projective_readout(self):
        data=write(1,"finite_dark",0,8,.35,0)
        bit,q,post=read(data,32,.2)
        self.assertEqual(bit,1)
        self.assertAlmostEqual(q["readable_probability"],1)
        self.assertLess(q["trace_error"],1e-10)
        self.assertGreaterEqual(q["min_eigenvalue"],-1e-10)
        self.assertAlmostEqual(np.trace(unpack(post["rho"])).real,1)

    def test_static_channel_does_not_load_dark(self):
        data=write(0,"finite_static",0,8,.35,0)
        _,rho=evolved(data,32)
        self.assertAlmostEqual(abs(rho[2,2]),0)

    def test_spectral_measure_normalization(self):
        atoms=response(8,.35,.03)
        total=sum((unpack(x["weight"]) for x in atoms), np.zeros((2,2),complex))
        np.testing.assert_allclose(total,np.eye(2),atol=1e-10)

    def test_rng_is_addressed_not_sequential(self):
        a={str(i):uniform(9,"event",i) for i in range(12)}
        b={str(i):uniform(9,"event",i) for i in reversed(range(12))}
        self.assertEqual(a,b)
        self.assertTrue(all(0 < x < 1 for x in a.values()))

    def test_r124_analytic_weight_control(self):
        rows=list(exact_histories())
        self.assertEqual(sum(w for _,_,w in rows),1)
        self.assertEqual(sum(w for _,bits,w in rows if bits==[1,1]),F(5,16))

    def test_existential_is_not_universal_closure(self):
        r=finite_closure({0},{0:[0,1]})
        self.assertTrue(r["exists_successor"])
        self.assertFalse(r["universal"])


if __name__ == "__main__":
    unittest.main()
