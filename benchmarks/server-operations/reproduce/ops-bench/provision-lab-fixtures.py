"""Provision a fresh, pinned disposable guest only; never a scored snapshot."""
from pathlib import Path
import argparse, subprocess, sys
from ssh_lab import command, upload

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--fresh-build',action='store_true',required=True);p.parse_args()
    probe=command("set -eu\ntest \"$(hostname)\" = ops-lab\ntest -f /var/lib/ops-harness/provision-complete\ntest ! -e /var/lib/ops-harness/main-snapshot-marker\ntest ! -e /var/lib/ops-harness/fixture-bootstrap-started\n",timeout=15)
    if probe.returncode:raise RuntimeError('Target is not an unused disposable build guest; refusing fixture changes')
    marker=command('touch /var/lib/ops-harness/fixture-bootstrap-started\n',timeout=10)
    if marker.returncode:raise RuntimeError('Cannot record fresh provision boundary')
    # The cloud-image marker is required before any mutation. Separate management
    # credentials and generated host pin are used for all these owner-side steps.
    for name in ['identity-fixture.py','worker_crash_fixture.py','harness_verify.py']:
        upload(ROOT/name,'/opt/ops-lab/'+name)
    order=['prepare-fixtures.py','prepare-pki.py','prepare-identity.py','prepare-variants.py','prepare-failure-fixtures.py','prepare-main-fixtures.py','install-executor.py']
    for name in order:
        subprocess.run([sys.executable,str(ROOT/name)],cwd=ROOT,check=True)
    result=command('set -eu\npython3 /opt/ops-lab/fixture-reset.py N01 0\ncurl -fsS http://127.0.0.1:18880/health\n',timeout=90)
    if result.returncode or 'OPS_LAB_V0_OK' not in result.stdout:raise RuntimeError('Fixture bootstrap health verification failed')
    result=command('cat /var/lib/ops-harness/fault-ssh/old.pub\n',timeout=10)
    if result.returncode:raise RuntimeError('Cannot pin fresh fault-path key')
    parts=result.stdout.strip().split()
    if len(parts)<2 or parts[0]!='ssh-ed25519':raise RuntimeError('Unexpected fault host key')
    private=ROOT/'lab-private';pin=private/'known_hosts_fault'
    pin.write_text('[127.0.0.1]:22220 '+parts[0]+' '+parts[1]+'\n');pin.chmod(0o600)
    result=command('touch /var/lib/ops-harness/fixture-bootstrap-complete\nsync\n',timeout=10)
    if result.returncode:raise RuntimeError('Cannot finish fixture provision marker')
    print('Fresh disposable fixtures provisioned and independently healthy. No model was called.')

if __name__=='__main__':main()
