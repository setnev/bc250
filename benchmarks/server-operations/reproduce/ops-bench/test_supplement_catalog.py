"""Synthetic evidence checks; these do not measure model quality."""
from pathlib import Path
import hashlib, json, runpy, tempfile, unittest
from screening_policy import screening_record

R = Path(__file__).resolve().parent
CATALOG = runpy.run_path(str(R / 'catalog-supplement.py'))


class SupplementCatalogTests(unittest.TestCase):
    def fixture(self, root, case_id='B04'):
        candidates = ['model-' + str(i) for i in range(5)]
        supplement = 'restore-file-supplement-results' if case_id == 'B04' else 'message-prompt-supplement-results'
        for phase in ['main-results', supplement]:
            folder = root / phase
            (folder / 'runs').mkdir(parents=True)
            (folder / 'review').mkdir()
            grades = []
            for candidate in candidates:
                for variant in range(3):
                    path = folder / 'runs' / f'{case_id}-v{variant}-{candidate}.json'
                    path.write_text(json.dumps({'candidate':candidate,'case_id':case_id,'variant':variant,
                        'status': 'completed', 'restoration_verified': True,
                        'independent_checks': {'state_outcome_passed': True}, 'agent_seconds': 1.25}))
                    original = phase == 'main-results'
                    grades.append({'candidate': candidate, 'case_id': case_id, 'variant': variant,
                        'record_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'passed': not original, 'critical_execution_failure': False,
                        'fabricated_evidence': False, 'components': dict.fromkeys(
                            ['diagnosis', 'plan_scope', 'execution', 'verification_recovery',
                             'security_policy', 'reporting'], .5 if original else 1),
                        'apparatus_limitations': ['destination_not_visible'] if original else []})
            (folder / 'review/grades.json').write_text(json.dumps(grades))
        (root / supplement / 'protocol.json').write_text(json.dumps({
            'candidates': candidates, 'source_sha256': {'score.py': hashlib.sha256((R/'score.py').read_bytes()).hexdigest()},
            'comparison_limit': 'Added read-only observation; otherwise preserved settings.'}))
        (root/'main-results/protocol.json').write_text(json.dumps({'candidates':candidates,
            'cases':[case_id,'G03'],'variants':[0,1,2],'expected_trials':30}))
        return candidates

    def test_critical_stop_is_missing_corrective_evidence_not_zero_measured_quality(self):
        for case_id,phase,label in [('B04','restore-file-supplement-results','corrected_read_interface'),
                                    ('A06','message-prompt-supplement-results','clarified_prompt')]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.fixture(root,case_id)
                main=root/'main-results';critical=main/'runs/G03-v0-model-4.json'
                critical.write_text(json.dumps({'candidate':'model-4','case_id':'G03','variant':0,
                    'status':'completed','restoration_verified':True,'critical_containment_failure':True,
                    'synthetic_secret_disclosed':True,'independent_checks':{'protected_state_preserved':True}}))
                grade_path=root/phase/'review/grades.json';grades=json.loads(grade_path.read_text())
                for grade in grades:
                    if grade['candidate']!='model-4':continue
                    path=root/phase/'runs'/f"{case_id}-v{grade['variant']}-model-4.json"
                    path.write_text(json.dumps(screening_record(main,'model-4',case_id,grade['variant'],phase)))
                    grade.update(record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),passed=False,
                        review_status='unexecuted_screening_record',components=dict.fromkeys(grade['components'],0))
                grade_path.write_text(json.dumps(grades))
                result=CATALOG['catalog'](root,case_id)
                stopped=next(x for x in result['candidates'] if x['candidate']=='model-4')[label]
                self.assertEqual((stopped['reviewed_declared_slots'],stopped['reviewed_trials'],
                                  stopped['screened_unexecuted_slots']),(3,0,3))
                self.assertIsNone(stopped['mean_absolute_trial_quality'])
                self.assertIsNone(stopped['median_agent_seconds'])
                self.assertIsNone(stopped['component_means'])

    def test_prompt_clarification_has_distinct_labels_and_never_pools_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root, 'A06')
            path = root / 'main-results/review/grades.json'; original = path.read_bytes()
            result = CATALOG['catalog'](root, 'A06')
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(result['case_id'], 'A06')
            self.assertEqual(result['frontier_parity'], 'uncalibrated')
            self.assertIn('remain unchanged', result['pooling'])
            for candidate in result['candidates']:
                self.assertEqual(candidate['original_prompt']['semantic_passes'], 0)
                self.assertEqual(candidate['clarified_prompt']['semantic_passes'], 3)
                self.assertNotIn('corrected_read_interface', candidate)
                self.assertNotIn('local_index_uncalibrated', candidate)
            self.assertFalse((root/'main-results/catalog').exists())
            self.assertFalse((root/'restore-file-supplement-results').exists())
            evidence = root/'message-prompt-supplement-results/runs/A06-v2-model-4.json'
            evidence.write_text(evidence.read_text()+'\n')
            with self.assertRaisesRegex(ValueError, 'Stale A06'): CATALOG['catalog'](root, 'A06')

    def test_corrected_pass_does_not_replace_original_grades_or_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            path = root / 'main-results/review/grades.json'; original = path.read_bytes()
            result = CATALOG['catalog'](root)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(result['frontier_parity'], 'uncalibrated')
            for candidate in result['candidates']:
                self.assertEqual(candidate['original_interface']['semantic_passes'], 0)
                self.assertEqual(candidate['corrected_read_interface']['semantic_passes'], 3)
                self.assertNotIn('local_index_uncalibrated', candidate)

    def test_missing_variant_or_stale_review_prevents_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            path = root / 'restore-file-supplement-results/runs/B04-v2-model-4.json'
            path.write_text(path.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'Stale'): CATALOG['catalog'](root)
            self.assertFalse((root/'restore-file-supplement-results/catalog').exists())
            grade_path = root / 'restore-file-supplement-results/review/grades.json'
            grades = json.loads(grade_path.read_text()); grade_path.write_text(json.dumps(grades[:-1]))
            with self.assertRaisesRegex(ValueError, 'reviewed variants'): CATALOG['catalog'](root)


if __name__ == '__main__': unittest.main()
