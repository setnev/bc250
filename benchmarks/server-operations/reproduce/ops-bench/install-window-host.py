"""Install a new bounded window definition; never start inference here."""
from pathlib import Path
import io, subprocess, sys, tarfile
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from remote import ssh_args

ROOT=Path(__file__).resolve().parent

def main():
    script='''set -eu
test -d /opt/bc250-mod-prep/ops-bench/lab
test ! -e /opt/bc250-mod-prep/ops-bench/restore-state.json
test ! -e /etc/systemd/system/bc250-ops-window.service
test -x /opt/bc250-ai/llama.cpp/build/bin/llama-server
test -f /usr/local/libexec/bc250-profile-clock.py
'''
    subprocess.run(ssh_args()+['sudo -n bash -s'],input=script,text=True,check=True)
    files=['bench-window.py','restore.py','models.ini']
    child=subprocess.Popen(ssh_args()+['sudo -n tar -x -f - -C /opt/bc250-mod-prep/ops-bench'],stdin=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=child.stdin,mode='w|') as tar:
            for name in files:tar.add(ROOT/name,arcname=name,recursive=False)
        child.stdin.close()
        if child.wait():raise RuntimeError('Window source transfer failed')
    finally:
        if child.poll() is None:child.terminate();child.wait()
    unit=(ROOT/'bc250-ops-window.service').read_text()
    subprocess.run(ssh_args()+['sudo -n bash -s'],input='set -eu\ncat > /etc/systemd/system/bc250-ops-window.service <<\'UNIT\'\n'+unit+'UNIT\nsystemctl daemon-reload\n',text=True,check=True)
    print('Window unit installed; main runner starts/stops it and verifies production recovery.')

if __name__=='__main__':main()
