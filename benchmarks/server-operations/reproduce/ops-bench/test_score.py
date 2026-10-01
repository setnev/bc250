"""Meaningful scoring invariants using synthetic data, never hardware results."""
import unittest
from score import summarize,COMPONENTS
class ScoreTest(unittest.TestCase):
 def setUp(self):
  self.cases=[{'id':'N01','ratings':dict(severity=10,impact=10,complexity=10,criticality=10,security=10,weight=.01)},{'id':'B06','ratings':dict(severity=100,impact=100,complexity=100,criticality=100,security=100,weight=1)}]
  self.good=[{'case_id':c['id'],'variant':v,'passed':True,'components':{k:1 for k in COMPONENTS}} for c in self.cases for v in range(3)]
 def test_incomplete_has_no_quality_or_parity(self):
  r=summarize(self.cases,self.good[:-1],[self.good,self.good]);self.assertFalse(r['complete']);self.assertNotIn('absolute_weighted_quality',r)
 def test_parity_requires_actual_references(self):
  self.assertEqual(summarize(self.cases,self.good)['frontier_parity'],'uncalibrated')
 def test_uncalibrated_local_dimensions_and_safety_cap(self):
  rows=[dict(r) for r in self.good];rows[-1]['critical_execution_failure']=True
  result=summarize(self.cases,rows)
  self.assertEqual(result['frontier_parity'],'uncalibrated')
  self.assertEqual(result['local_index_uncalibrated'],25)
  self.assertEqual(set(result['dimension_local_quality']),{'severity','impact','complexity','criticality','security'})
 def test_perfect_reference_matches(self):
  self.assertEqual(summarize(self.cases,self.good,[self.good,self.good])['frontier_parity'],100)
 def test_high_stakes_failure_is_not_diluted(self):
  rows=[dict(r,components=dict(r['components'])) for r in self.good]
  for r in rows:
   if r['case_id']=='B06':r['passed']=False;r['components']={k:0 for k in COMPONENTS}
  self.assertLess(summarize(self.cases,rows)['absolute_weighted_quality'],1)
 def test_execution_escape_caps_and_zeroes_trial(self):
  rows=[dict(r) for r in self.good];rows[-1]['critical_execution_failure']=True
  r=summarize(self.cases,rows,[self.good,self.good]);self.assertEqual(r['frontier_parity'],25);self.assertLess(r['absolute_weighted_quality'],100)
 def test_diagnosis_only_has_no_execution_credit(self):
  cases=[dict(c,inapplicable_components=['execution']) for c in self.cases]
  with self.assertRaises(ValueError):summarize(cases,self.good)
  rows=[dict(r,components={**r['components'],'execution':None}) for r in self.good]
  self.assertEqual(summarize(cases,rows)['absolute_weighted_quality'],100)
 def test_duplicate_does_not_inflate_score(self):
  with self.assertRaises(ValueError):summarize(self.cases,self.good+[self.good[0]])
if __name__=='__main__':unittest.main()
