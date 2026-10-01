"""Synthetic preflight-integrity tests, not real gateway or model evidence."""
from pathlib import Path
import json, tempfile, unittest
from soak_preflight import digest, validate_smoke


def smoke_fixture(root):
    selection = {'candidate': 'qwen3.5-9b', 'routine_cases': ['N01']}
    selection_path = root/'soak-selection.json'; selection_path.write_text(json.dumps(selection))
    source = root/'smoke-dummy.py'; source.write_text('# Synthetic source\n')
    folder = root/'soak-smoke-results'; folder.mkdir()
    (folder/'sources').mkdir(); (folder/'sources'/source.name).write_bytes(source.read_bytes())
    (folder/'review').mkdir()
    (folder/'protocol.json').write_text(json.dumps({'phase': 'production-gateway-smoke',
        'candidate': selection['candidate'], 'selection_sha256': digest(selection_path),
        'timed_soak_evidence': False, 'source_sha256': {source.name: digest(source)}}))
    (folder/'completion.json').write_text(json.dumps({'complete': True, 'errors': [], 'production_recovery_exit_code': 0}))
    jobs = []; grades = []
    for ident, case, variant in [('routine-preflight', 'N01', 0), ('fault-preflight', 'F05', 1)]:
        path = folder/'runs'/ident/'runs/trial.json'; path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'candidate': selection['candidate'], 'case_id': case, 'variant': variant,
            'status': 'completed', 'restoration_verified': True, 'critical_containment_failure': False,
            'fault_injection': {'inference_http': {'faults': 2, 'active': 0}}}))
        jobs.append({'id': ident, 'case': case, 'variant': variant, 'status': 'completed',
            'restoration_verified': True, 'critical_containment_failure': False})
        grades.append({'job_id': ident, 'record_sha256': digest(path), 'passed': False,
            'reviewer': 'independent Codex transcript review'})
    (folder/'jobs.json').write_text(json.dumps(jobs)); (folder/'review/grades.json').write_text(json.dumps(grades))
    return selection_path, selection


class SmokeTests(unittest.TestCase):
    def test_semantic_failure_is_visible_but_not_transport_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path, selection=smoke_fixture(root)
            result=validate_smoke(root,path,selection)
            self.assertEqual(result['semantic_passes'],0)
            self.assertFalse(result['timed_soak_evidence'])

    def test_changed_selection_source_or_transcript_is_rejected(self):
        for which in ['selection','source','transcript']:
            with self.subTest(which=which), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); path, selection=smoke_fixture(root)
                altered={'selection':path,'source':root/'smoke-dummy.py',
                    'transcript':root/'soak-smoke-results/runs/routine-preflight/runs/trial.json'}[which]
                altered.write_text(altered.read_text()+'\n')
                with self.assertRaises(AssertionError):validate_smoke(root,path,selection)

    def test_missing_review_and_failed_restoration_are_rejected(self):
        for which in ['review','restoration']:
            with self.subTest(which=which), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); path, selection=smoke_fixture(root); folder=root/'soak-smoke-results'
                changed=folder/('review/grades.json' if which=='review' else 'jobs.json')
                data=json.loads(changed.read_text())
                if which=='review':data.pop()
                else:data[0]['restoration_verified']=False
                changed.write_text(json.dumps(data))
                with self.assertRaises(AssertionError):validate_smoke(root,path,selection)

    def test_fault_evidence_must_be_real_two_responses_and_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path, selection=smoke_fixture(root); folder=root/'soak-smoke-results'
            transcript=folder/'runs/fault-preflight/runs/trial.json'; record=json.loads(transcript.read_text())
            record['fault_injection']['inference_http']['faults']=0; transcript.write_text(json.dumps(record))
            grade_path=folder/'review/grades.json'; grades=json.loads(grade_path.read_text())
            grades[1]['record_sha256']=digest(transcript); grade_path.write_text(json.dumps(grades))
            with self.assertRaises(AssertionError):validate_smoke(root,path,selection)


if __name__=='__main__':unittest.main()
