"""Real production gateway/controller preflight, separate from the timed soak."""
from pathlib import Path
import argparse, fcntl, importlib.util, json, shutil, subprocess, threading, time
import agent_core, soak_api
from message_supplement import validate as validate_message_supplement
from fault_proxy import Server

R = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('soak_driver', R/'soak-bench.py')
soak = importlib.util.module_from_spec(spec); spec.loader.exec_module(soak)
driver = soak.driver


def idle(samples, deadline=45):
    until = time.monotonic() + deadline
    while True:
        sample = soak.telemetry()
        samples.append(sample)
        hardware = sample['hardware']
        if hardware.get('latched') or hardware['temperature_c'] >= 85:
            raise RuntimeError('Production guard latched or temperature threshold reached')
        if sample['host']['memory_kib']['MemAvailable'] < 512*1024:
            raise RuntimeError('Host memory reserve below512MiB')
        if (hardware['cpu']['mode'] == 'idle' and
                hardware['cpu']['latency_request_us'] is None and
                hardware['cpu']['lease_remaining_s'] == 0 and not hardware['latched']):
            return sample
        if time.monotonic() >= until:
            raise RuntimeError('Production CPU/profile did not release to idle within45s')
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--selection', type=Path, required=True)
    args = parser.parse_args()
    lock = (R/'main-runner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert json.loads((R/'after-comparison-state.json').read_text())['status'].startswith('latency_completed')
    supplement = R/'restore-file-supplement-results'
    assert json.loads((supplement/'coverage.json').read_text())['recorded_trials'] == 15
    assert len(json.loads((supplement/'review/grades.json').read_text())) == 15
    message_proof=validate_message_supplement(R)
    selection, cases = soak.validate_selection(args.selection)
    folder = R/'soak-smoke-results'
    folder.mkdir(exist_ok=False)
    (folder/'sources').mkdir(); (folder/'runs').mkdir()
    names = driver.SOURCES + ['production-soak-smoke.py', 'soak-bench.py', 'soak_api.py',
                             'capture-soak-runtime.py', 'soak-projection-manifest.json', 'soak-runtime-pins.json', 'soak_preflight.py', 'message_supplement.py', 'screening_policy.py']
    for name in names: shutil.copy2(R/name, folder/'sources'/name)
    runtime_spec = importlib.util.spec_from_file_location('runtime', R/'capture-soak-runtime.py')
    runtime = importlib.util.module_from_spec(runtime_spec); runtime_spec.loader.exec_module(runtime)
    driver.atomic(folder/'protocol.json', {
        'phase': 'production-gateway-smoke', 'candidate': selection['candidate'],
        'selection_sha256': soak.digest(args.selection), 'unscored_apparatus_preflight': True,
        'message_prompt_supplement':message_proof,
        'source_sha256': {n: soak.digest(R/n) for n in names},
        'timed_soak_evidence': False, 'frontier_parity': 'uncalibrated',
        'jobs': 'One selected routine case and F05-v1 through the real gateway; independent semantic review required.'})
    driver.atomic(folder/'runtime-configuration.json', runtime.capture(selection['candidate']))
    proxy = None; forwarding = None; original_api = agent_core.api
    rows = []; samples = []; errors = []; recovery = None
    try:
        initial = idle(samples); driver.atomic(folder/'initial-state.json', initial)
        proxy = Server(18121, 'http://127.0.0.1:18123')
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        forwarding = soak_api.forwarding_server(); agent_core.api = soak_api.api
        for job_id, case, variant in [('routine-preflight', selection['routine_cases'][0], 0),
                                      ('fault-preflight', 'F05', 1)]:
            job_folder = folder/'runs'/job_id
            job_folder.mkdir(); (job_folder/'runs').mkdir()
            record = driver.evaluate(selection['candidate'], cases[case], variant, job_folder, 'production-gateway-smoke')
            row = {'id': job_id, 'kind': 'smoke', 'case': case, 'variant': variant,
                   'status': record['status'], 'restoration_verified': record['restoration_verified'],
                   'critical_containment_failure': record['critical_containment_failure'],
                   'semantic_review': 'pending; not part of comparison or timed soak'}
            rows.append(row); driver.atomic(folder/'jobs.json', rows)
            assert record['status'] == 'completed' and record['restoration_verified'] and not record['critical_containment_failure']
            if case == 'F05':
                fault = record['fault_injection']['inference_http']
                assert fault['faults'] == 2 and fault['active'] == 0, 'Real two503 injection/release not demonstrated'
            observed = idle(samples)
            assert observed['host']['boot_id'] == initial['host']['boot_id']
            for unit, before in initial['host']['services'].items():
                after = observed['host']['services'][unit]
                assert after['ActiveState'] == 'active' and after['MainPID'] == before['MainPID'] and after['NRestarts'] == before['NRestarts']
            print(json.dumps(row), flush=True)
    except BaseException as error:
        errors.append({'type': type(error).__name__, 'detail': str(error)})
        raise
    finally:
        agent_core.api = original_api
        for server in [proxy, forwarding]:
            if server is not None: server.shutdown(); server.server_close()
        try: driver.atomic(folder/'final-snapshot-restoration.json', driver.restore())
        except Exception as error: errors.append({'stage': 'restore', 'type': type(error).__name__, 'detail': str(error)})
        recovery = subprocess.run(['python3', str(R/'check-recovery.py')], capture_output=True, text=True, timeout=60)
        driver.atomic(folder/'production-recovery.json', {'exit_code': recovery.returncode, 'stdout': recovery.stdout, 'stderr': recovery.stderr})
        driver.atomic(folder/'telemetry.json', samples)
        driver.atomic(folder/'completion.json', {'complete': len(rows) == 2 and not errors and recovery.returncode == 0,
            'errors': errors, 'production_recovery_exit_code': recovery.returncode,
            'semantic_review': 'pending; apparatus completion does not establish semantic success', 'timed_soak_evidence': False})
    assert not errors and recovery.returncode == 0


if __name__ == '__main__': main()
