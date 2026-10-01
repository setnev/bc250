"""Require current, real and independently reviewed gateway preflight evidence."""
from pathlib import Path
import hashlib, json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_smoke(root, selection_path, selection):
    folder = root / 'soak-smoke-results'
    protocol = json.loads((folder/'protocol.json').read_text())
    completion = json.loads((folder/'completion.json').read_text())
    assert protocol['phase'] == 'production-gateway-smoke' and not protocol['timed_soak_evidence']
    assert protocol['candidate'] == selection['candidate']
    assert protocol['selection_sha256'] == digest(selection_path), 'Smoke used different workload selection'
    for name, pin in protocol['source_sha256'].items():
        assert digest(root/name) == pin and digest(folder/'sources'/name) == pin, 'Smoke implementation changed'
    assert completion['complete'] and not completion['errors'] and completion['production_recovery_exit_code'] == 0
    jobs = json.loads((folder/'jobs.json').read_text())
    grades = json.loads((folder/'review/grades.json').read_text())
    expected = {'routine-preflight': (selection['routine_cases'][0], 0), 'fault-preflight': ('F05', 1)}
    assert len(jobs) == len(grades) == 2
    assert {j['id'] for j in jobs} == {g['job_id'] for g in grades} == set(expected)
    for job in jobs:
        case, variant = expected[job['id']]
        assert (job['case'], job['variant']) == (case, variant)
        assert job['status'] == 'completed' and job['restoration_verified'] and not job['critical_containment_failure']
        paths = list((folder/'runs'/job['id']/'runs').glob('*.json'))
        assert len(paths) == 1
        record = json.loads(paths[0].read_text())
        grade = next(g for g in grades if g['job_id'] == job['id'])
        assert grade['record_sha256'] == digest(paths[0]), 'Stale smoke transcript review'
        assert grade['reviewer'] == 'independent Codex transcript review'
        assert (record['candidate'], record['case_id'], record['variant']) == (selection['candidate'], case, variant)
        assert record['status'] == 'completed' and record['restoration_verified'] and not record['critical_containment_failure']
        if case == 'F05':
            fault = record['fault_injection']['inference_http']
            assert fault['faults'] == 2 and fault['active'] == 0
    # Quality failures remain publishable findings, not hidden by a launch gate.
    # This gate proves transport/containment/recovery and completed review only.
    return {'protocol_sha256': digest(folder/'protocol.json'),
            'completion_sha256': digest(folder/'completion.json'),
            'reviews_sha256': digest(folder/'review/grades.json'),
            'semantic_passes': sum(g['passed'] for g in grades),
            'timed_soak_evidence': False}
