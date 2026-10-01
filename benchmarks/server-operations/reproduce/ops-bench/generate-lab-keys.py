"""Generate private test-only keys for a new reproducer; publish none of them."""
from pathlib import Path
import subprocess

private=Path(__file__).resolve().parent/'lab-private';private.mkdir(mode=0o700,exist_ok=True)
for name in ['harness_key','executor_key','guest_host_key']:
    path=private/name
    if path.exists():raise RuntimeError('Existing lab keys retained; use a fresh lab-private directory')
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','fixture','-f',str(path)],check=True)
host=(private/'guest_host_key.pub').read_text().split()
(private/'known_hosts').write_text('[127.0.0.1]:22219 '+' '.join(host[:2])+'\n')
(private/'known_hosts').chmod(0o600)
print('Private lab keys generated; management pin derives from the generated guest key.')
