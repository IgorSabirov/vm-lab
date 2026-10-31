import unittest
from e002e_exp.runtime import memory_preflight,compare_environment

class ResourceControls(unittest.TestCase):
    def env(self):
        return dict(python='p',platform='linux',machine='x86_64',cpu_model='cpu',logical_cpus=8,affinity=list(range(8)),numpy='1',scipy='1',threadpools=[],requested_threads={'OPENBLAS_NUM_THREADS':'1'},blas_library_identity=[{'path':'blas','sha256':'a'*64}],cgroup_visibility='NOT_MOUNTED_IN_JOB_NAMESPACE',address_space_rlimit=[10000,10000],process_vm_size_bytes=1000,memory_available='100 kB',memory_limit=None,memory_current=None,cpu_quota=None)
    def budget(self):
        return dict(peak_additional_bytes=3000,reserve_bytes=1000,measured_peak_rss_bytes=1000,simultaneous_factor_storage_bytes=500,measured_peak_vm_bytes=2000)
    def test_enforced_limit_and_blas_identity_allow_comparison(self):
        self.assertTrue(compare_environment(self.env(),self.env())['comparable'])
        self.assertEqual(memory_preflight(self.budget(),self.env())['available_bytes'],9000)
    def test_unknown_limit_is_not_substituted_by_host_ram(self):
        e=self.env();e['address_space_rlimit']=[-1,-1]
        self.assertFalse(compare_environment(e,e)['comparable'])
        with self.assertRaises(ValueError):memory_preflight(self.budget(),e)
    def test_address_space_or_virtual_peak_shortfall_rejected(self):
        e=self.env();e['process_vm_size_bytes']=7000
        with self.assertRaises(MemoryError):memory_preflight(self.budget(),e)
        b=self.budget();b['measured_peak_vm_bytes']=4000
        with self.assertRaises(ValueError):memory_preflight(b,self.env())
    def test_changed_blas_cannot_reuse_calibration(self):
        e=self.env();e['blas_library_identity']=[{'path':'different','sha256':'b'*64}]
        self.assertFalse(compare_environment(self.env(),e)['comparable'])
