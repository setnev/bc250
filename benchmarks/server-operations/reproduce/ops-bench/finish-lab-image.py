"""Cleanly stop a fresh provisioned build VM and export private golden disks."""
from pathlib import Path
import hashlib, json, subprocess, time
from ssh_lab import command

ROOT=Path(__file__).resolve().parent/'lab-build'
IMAGE='anthos-ops-qemu:20260930'

def docker_tool(*args):
    subprocess.run(['docker','run','--rm','-v',str(ROOT)+':/lab','--entrypoint',args[0],IMAGE,*args[1:]],check=True)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024**2),b''):h.update(chunk)
    return h.hexdigest()

def main():
    for name in ['golden.qcow2','data-golden.qcow2']:
        if (ROOT/name).exists():raise RuntimeError('Refusing to replace an existing exported golden: '+name)
    p=command('set -eu\ntest "$(hostname)" = ops-lab\ntest -f /var/lib/ops-harness/fixture-bootstrap-complete\ntest ! -e /var/lib/ops-harness/main-snapshot-marker\nsync\nsystemctl poweroff\n',timeout=15)
    if p.returncode not in (0,255):raise RuntimeError('Build guest clean shutdown was not requested successfully')
    deadline=time.monotonic()+60
    while subprocess.check_output(['docker','inspect','-f','{{.State.Running}}','anthos-ops-lab'],text=True).strip()=='true':
        if time.monotonic()>deadline:raise RuntimeError('Guest did not shut down cleanly; refusing disk export')
        time.sleep(1)
    docker_tool('qemu-img','convert','-f','qcow2','-O','qcow2','/lab/work.qcow2','/lab/golden.qcow2')
    docker_tool('qemu-img','convert','-f','qcow2','-O','qcow2','/lab/data.qcow2','/lab/data-golden.qcow2')
    # Keep the ext4 filesystem at128MiB; M07 must perform the real filesystem grow.
    docker_tool('qemu-img','resize','/lab/data-golden.qcow2','192M')
    manifest={name:{'sha256':sha(ROOT/name),'bytes':(ROOT/name).stat().st_size} for name in ['golden.qcow2','data-golden.qcow2','seed.iso']}
    manifest['privacy']='Private generated lab images and seed contain test-only SSH keys/certificates. Do not commit or upload them.'
    (ROOT/'generated-image-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Private lab golden disks exported; data virtual capacity192MiB, filesystem remains128MiB.')

if __name__=='__main__':main()
