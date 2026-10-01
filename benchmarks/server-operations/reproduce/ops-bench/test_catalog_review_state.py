"""A catalog must not request already reviewed work or hide stale evidence."""
from pathlib import Path
import contextlib, hashlib, io, json, runpy, tempfile, unittest

catalog=runpy.run_path(str(Path(__file__).with_name('catalog-results.py')))['catalog']

def fixture(root):
    (root/'runs').mkdir();(root/'sources').mkdir();(root/'review').mkdir()
    (root/'protocol.json').write_text(json.dumps({'candidates':['test-model'],'cases':['N01','N02'],'variants':[0]}))
    ratings={k:50 for k in ['severity','impact','complexity','criticality','security','risk']};ratings['weight']=.25
    (root/'sources/cases.json').write_text(json.dumps([{'id':c,'ratings':ratings} for c in ['N01','N02']]))
    paths=[]
    for case in ['N01','N02']:
        p=root/'runs'/f'{case}-v0-test-model.json'
        p.write_text(json.dumps({'candidate':'test-model','case_id':case,'variant':0,'status':'completed'}));paths.append(p)
    grade={'candidate':'test-model','case_id':'N01','variant':0,'record_sha256':hashlib.sha256(paths[0].read_bytes()).hexdigest()}
    (root/'review/grades.json').write_text(json.dumps([grade]));return grade,paths

class CatalogReviewTests(unittest.TestCase):
    def test_partial_review_keeps_only_unreviewed_trial_in_queue(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);fixture(root);catalog(root)
            queue=json.loads((root/'catalog/review-queue.json').read_text())
            self.assertEqual([r['case_id'] for r in queue],['N02'])
            rows=json.loads((root/'catalog/trials.json').read_text())
            self.assertEqual([r['semantic_review'] for r in rows],['sha_bound_review_available','pending'])
            self.assertTrue(all(r['quality_score'] is None for r in json.loads((root/'catalog/progress-summary.json').read_text())))

    def test_changed_transcript_cannot_be_hidden_as_reviewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grade,paths=fixture(root);paths[0].write_text(paths[0].read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'Stale'):catalog(root)
            self.assertFalse((root/'catalog').exists())

    def test_duplicate_review_is_not_accepted_as_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grade,_=fixture(root);(root/'review/grades.json').write_text(json.dumps([grade,grade]))
            with self.assertRaisesRegex(ValueError,'Duplicate review'):catalog(root)
            self.assertFalse((root/'catalog').exists())

if __name__=='__main__':unittest.main()
