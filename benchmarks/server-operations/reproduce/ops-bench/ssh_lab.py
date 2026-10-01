"""Pinned SSH access to the disposable guest; harness credentials stay private."""
from pathlib import Path
import subprocess,json
root=Path(__file__).resolve().parent
private=root/'lab-private'
def ssh_args(executor=False,fault=False):
 if fault and not executor:raise ValueError('Management must use the unaffected SSH path')
 user='ops-executor' if executor else 'harness';key=private/('executor_key' if executor else 'harness_key')
 return ['ssh','-i',str(key),'-p','22220' if fault else '22219','-o','UserKnownHostsFile='+str(private/('known_hosts_fault' if fault else 'known_hosts')),'-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',user+'@127.0.0.1']
def command(script,timeout=30,executor=False,fault=False):
 if fault and not executor:raise ValueError('Management must use the unaffected SSH path')
 cmd=ssh_args(executor,fault)
 if executor:
  payload=json.dumps(script)+'\n'
 else:
  cmd+=['sudo -n bash -s'];payload=script
 return subprocess.run(cmd,input=payload,text=True,capture_output=True,timeout=timeout)

def upload(filename,guest_path):
 import base64,shlex
 data=base64.b64encode(Path(filename).read_bytes()).decode()
 p=command("printf '%s' "+shlex.quote(data)+' | base64 -d > '+shlex.quote(guest_path)+'\nchmod 644 '+shlex.quote(guest_path)+'\n')
 if p.returncode:raise RuntimeError(p.stderr)
 return p
