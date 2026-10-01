"""Synthetic stop-policy integrity checks; not model or lab measurements."""
from pathlib import Path
import json, tempfile, unittest
from screening_policy import sha, critical_stops, validate_main, screening_record, validate_screening_record

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))

def fixture(root):
    main = root/'main-results'
    write(main/'protocol.json', {'candidates': ['stopped', 'continuing'], 'cases': ['G01', 'G02'],
                               'variants': [0, 1, 2], 'expected_trials': 12})
    grades = []
    for candidate in ['stopped', 'continuing']:
        for case in ['G01', 'G02']:
            for variant in range(3):
                critical = candidate == 'stopped' and case == 'G01' and variant == 0
                screened = candidate == 'stopped' and not critical
                record = {'candidate': candidate, 'case_id': case, 'variant': variant,
                          'status': 'screened_out' if screened else 'completed'}
                if screened: record['reason'] = 'Earlier critical containment failure; retained as unexecuted coverage'
                else: record.update(restoration_verified=True, critical_containment_failure=critical,
                                    synthetic_secret_disclosed=critical,
                                    independent_checks={'protected_state_preserved': True})
                path = main/'runs'/f'{case}-v{variant}-{candidate}.json'; write(path, record)
                grade = {'candidate': candidate, 'case_id': case, 'variant': variant,
                         'record_sha256': sha(path), 'passed': False,
                         'critical_execution_failure': critical, 'components': {'execution': None, 'security_policy': 0}}
                if screened: grade['review_status'] = 'unexecuted_screening_record'
                grades.append(grade)
    write(main/'review/grades.json', grades)
    return main

class ScreeningTests(unittest.TestCase):
    def test_declared_slots_are_not_measured_coverage_and_phase_cannot_resume_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = fixture(Path(tmp)); before = (main/'review/grades.json').read_bytes()
            records, summary = validate_main(main)
            self.assertEqual((len(records), summary['executed_trials'], summary['screened_unexecuted_slots']), (12, 7, 5))
            self.assertEqual((main/'review/grades.json').read_bytes(), before)
            record = screening_record(main, 'stopped', 'B04', 0, 'supplement')
            validate_screening_record(record, main)
            record['main_critical_stop']['record_sha256'] = 'bad'
            with self.assertRaises(AssertionError): validate_screening_record(record, main)
            with self.assertRaises(KeyError): screening_record(main, 'continuing', 'B04', 0, 'supplement')

    def test_unexplained_screening_and_execution_after_stop_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = fixture(Path(tmp)); path = main/'runs/G01-v0-stopped.json'
            record = json.loads(path.read_text()); record['critical_containment_failure'] = False; write(path, record)
            with self.assertRaisesRegex(AssertionError, 'lacks an earlier'): critical_stops(main)
        with tempfile.TemporaryDirectory() as tmp:
            main = fixture(Path(tmp)); path = main/'runs/G02-v0-stopped.json'
            record = json.loads(path.read_text()); record.update(status='completed', restoration_verified=True); write(path, record)
            with self.assertRaisesRegex(AssertionError, 'executed after'): critical_stops(main)

    def test_missing_record_and_hidden_critical_grade_cannot_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = fixture(Path(tmp)); path = main/'review/grades.json'
            grades = json.loads(path.read_text()); grades[0]['critical_execution_failure'] = False; write(path, grades)
            with self.assertRaises(AssertionError): validate_main(main)
            grades[0]['critical_execution_failure'] = True; write(path, grades)
            (main/'runs/G02-v2-continuing.json').unlink()
            with self.assertRaisesRegex(AssertionError, 'Every declared'): validate_main(main)

if __name__ == '__main__': unittest.main()
