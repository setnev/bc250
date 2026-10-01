"""No matching kernel events is healthy; query failures must remain failures."""
from pathlib import Path
import importlib.util, unittest

spec=importlib.util.spec_from_file_location('soak_kernel',Path(__file__).with_name('soak-bench.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class KernelQueryTests(unittest.TestCase):
    def test_normal_no_match_status_does_not_abort(self):
        for code,output in [(1,''),(1,'-- No entries --\n'),(0,'')]:
            self.assertFalse(module.kernel_fault_result({'returncode':code,'stdout':output,'stderr':''}))

    def test_actual_gpu_oom_event_remains_a_fault(self):
        self.assertTrue(module.kernel_fault_result({'returncode':0,'stdout':'amdgpu: GPU reset begin!\n','stderr':''}))

    def test_real_query_failures_are_not_masked(self):
        for code,output,error in [(1,'','Permission denied'),(2,'','bad option'),(1,'unexpected output','')]:
            with self.assertRaises(RuntimeError):
                module.kernel_fault_result({'returncode':code,'stdout':output,'stderr':error})

if __name__=='__main__':unittest.main()
