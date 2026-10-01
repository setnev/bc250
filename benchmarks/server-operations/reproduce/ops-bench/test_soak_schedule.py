"""A soak must exercise every selected case's three approved variants."""
from pathlib import Path
import collections, importlib.util, unittest

spec=importlib.util.spec_from_file_location('soak_schedule',Path(__file__).with_name('soak-bench.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ScheduleTests(unittest.TestCase):
    def test_six_cases_have_balanced_variant_coverage(self):
        cases=['N04','N07','S04','S05','C01','C02'];schedule=module.build_schedule(cases)
        routine=[x for x in schedule if x['kind']=='routine']
        self.assertEqual(collections.Counter((x['case'],x['variant']) for x in routine),
                         collections.Counter({(c,v):16 for c in cases for v in range(3)}))
        self.assertEqual(sorted(x['offset'] for x in routine),list(range(0,86400,300)))
        self.assertEqual(len({x['id'] for x in schedule}),301)
        self.assertEqual(collections.Counter(x['kind'] for x in schedule),
                         {'routine':288,'fault':4,'queue':9})

    def test_fault_and_queue_schedule_remains_explicit_and_deterministic(self):
        cases=['N04','N07'];a=module.build_schedule(cases);self.assertEqual(a,module.build_schedule(cases))
        self.assertEqual([(x['case'],x['variant'],x['offset']) for x in a if x['kind']=='fault'],
                         [('F01',0,7320),('F05',1,28920),('F07',0,50520),('F08',0,72120)])
        for offset in (21720,43320,64920):
            self.assertEqual([x['variant'] for x in a if x['kind']=='queue' and x['offset']==offset],[0,1,2])

if __name__=='__main__':unittest.main()
