"""Reject stale or invalid review evidence before cataloging repeated jobs."""
import copy, hashlib, json, runpy, tempfile, unittest
from pathlib import Path

REVIEW = runpy.run_path(str(Path(__file__).with_name('soak-review.py')))

class SoakReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.record = {'candidate':'model','case_id':'N01','variant':0,'status':'completed',
                       'restoration_verified':True,'independent_checks':{'state_outcome_passed':True}}
        self.path = self.folder/'runs/routine-000/runs/transcript.json'
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(self.record))
        (self.folder/'jobs.json').write_text(json.dumps([{'id':'routine-000','status':'completed'}]))
        (self.folder/'sources').mkdir()
        (self.folder/'sources/evaluator-criteria.json').write_text(json.dumps([
            {'case_id':'N01','inapplicable_components':['execution']}]))
        self.grade = {'job_id':'routine-000','candidate':'model','case_id':'N01','variant':0,
                      'record_sha256':hashlib.sha256(self.path.read_bytes()).hexdigest(),
                      'components':{c:None if c=='execution' else 1 for c in REVIEW['COMPONENTS']},
                      'passed':True,'critical_execution_failure':False,'fabricated_evidence':False,
                      'reviewer':'independent Codex transcript review',
                      'rationale':'Synthetic complete transcript with observed verification and restoration.'}

    def commit(self, grade=None):
        return REVIEW['commit'](self.folder,[grade or self.grade])

    def test_stale_transcript_cannot_be_graded(self):
        self.path.write_text(json.dumps({**self.record,'status':'running'}))
        with self.assertRaises(AssertionError):self.commit()
        self.path.write_text(json.dumps({**self.record,'changed':True}))
        with self.assertRaisesRegex(AssertionError,'changed'):self.commit()

    def test_failed_state_cannot_be_claimed_pass(self):
        self.record['independent_checks']['state_outcome_passed']=False
        self.path.write_text(json.dumps(self.record))
        self.grade['record_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaises(AssertionError):self.commit()

    def test_inapplicable_component_cannot_inflate_credit(self):
        grade=copy.deepcopy(self.grade);grade['components']['execution']=1
        with self.assertRaises(AssertionError):self.commit(grade)

    def test_review_is_idempotent_but_not_overwritable(self):
        self.assertEqual(self.commit()['reviewed_soak_jobs'],1)
        self.assertEqual(self.commit()['reviewed_soak_jobs'],1)
        grade=copy.deepcopy(self.grade);grade['components']['diagnosis']=.5
        with self.assertRaisesRegex(AssertionError,'amendment'):self.commit(grade)

    def test_fabrication_prevents_pass(self):
        self.grade['fabricated_evidence']=True
        with self.assertRaises(AssertionError):self.commit()

if __name__=='__main__':unittest.main()
