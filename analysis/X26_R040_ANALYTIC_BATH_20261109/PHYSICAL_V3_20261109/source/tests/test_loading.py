import unittest
import numpy as np
from x26r040.loading import simulate_controlled_loading


class TestLoadingInterface(unittest.TestCase):
    def test_explicit_control_can_load_target_and_reports_missing_cost(self):
        H0=np.zeros((2,2),dtype=complex)
        Hc=np.array([[0,1],[1,0]],dtype=complex)
        psi0=np.array([1,0],dtype=complex)
        P=np.array([[0,0],[0,1]],dtype=complex)
        T=1.0
        u=lambda t: np.pi/T * np.sin(np.pi*t/T)**2
        du=lambda t: np.pi/T * np.sin(2*np.pi*t/T) * np.pi/T
        result=simulate_controlled_loading(H0,Hc,psi0,P,np.linspace(0,T,101),u,du)
        self.assertGreater(result["target_population"][-1],0.999999)
        self.assertEqual(result["actuator_cost_status"],"NOT_EVALUABLE_NO_ACTUATOR_AND_RESET_MODEL")
        self.assertIsNone(result["actuator_total_cost"])


if __name__ == "__main__":
    unittest.main()
