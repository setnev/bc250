"""Install a fresh restricted QEMU lab; refuse existing lab paths and units."""
from pathlib import Path
import hashlib, json, subprocess, sys, tarfile
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from remote import ssh_args

ROOT=Path(__file__).resolve().parent
DEST='/opt/bc250-mod-prep/ops-bench'

def remote(script):
    p=subprocess.run(ssh_args()+['sudo -n bash -s'],input=script,text=True,capture_output=True)
    if p.returncode:raise RuntimeError(p.stderr[-2000:])
    return p.stdout

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024**2),b''):h.update(chunk)
    return h.hexdigest()

def main():
    manifest=json.loads((ROOT/'lab-build/generated-image-manifest.json').read_text())
    files=[ROOT/'lab-build'/name for name in ['golden.qcow2','data-golden.qcow2','seed.iso']]
    for path in files:
        if sha(path)!=manifest[path.name]['sha256']:raise RuntimeError('Image hash changed: '+path.name)
    remote('set -eu\ntest ! -e '+DEST+'/lab\ntest ! -e /etc/systemd/system/bc250-ops-lab.service\ncommand -v qemu-system-x86_64 >/dev/null\ncommand -v qemu-img >/dev/null\ntest -c /dev/kvm\ntest ! -e /var/tmp/anthos-ops-new-lab\n')
    # Only explicit private image members; no management keys or folders.
    child=subprocess.Popen(ssh_args()+['sudo -n tar -x -f - -C /var/tmp'],stdin=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=child.stdin,mode='w|') as tar:
            for path in files:tar.add(path,arcname='anthos-ops-new-lab/'+path.name,recursive=False)
        child.stdin.close()
        if child.wait():raise RuntimeError('Pinned image transfer failed')
    finally:
        if child.poll() is None:child.terminate();child.wait()
    verification=''.join(f'echo {manifest[path.name]["sha256"]}  /var/tmp/anthos-ops-new-lab/{path.name} | sha256sum -c -\n' for path in files)
    unit=(ROOT/'bc250-ops-lab.service').read_text()
    remote('set -eu\n'+verification+'''test ! -e /opt/bc250-mod-prep/ops-bench/lab
if ! id bc250-ops-vm >/dev/null 2>&1; then useradd --system --no-create-home --shell /usr/sbin/nologin bc250-ops-vm; fi
usermod -a -G kvm bc250-ops-vm
install -d -m 0750 -o bc250-ops-vm -g bc250-ops-vm /opt/bc250-mod-prep/ops-bench/lab
for name in golden.qcow2 data-golden.qcow2 seed.iso; do
 install -m 0640 -o bc250-ops-vm -g bc250-ops-vm /var/tmp/anthos-ops-new-lab/$name /opt/bc250-mod-prep/ops-bench/lab/$name
done
cd /opt/bc250-mod-prep/ops-bench/lab
runuser -u bc250-ops-vm -- qemu-img create -f qcow2 -F qcow2 -b golden.qcow2 work.qcow2
runuser -u bc250-ops-vm -- qemu-img create -f qcow2 -F qcow2 -b data-golden.qcow2 data-work.qcow2
cat > /etc/systemd/system/bc250-ops-lab.service <<'UNIT'
'''+unit+'''UNIT
systemctl daemon-reload
systemctl start bc250-ops-lab.service
systemctl is-active bc250-ops-lab.service
''')
    print('Fresh restricted lab launched; verify pinned guest health before freezing.')

if __name__=='__main__':main()
