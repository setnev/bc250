"""Owner-configured inference-host control, outside the model tool boundary."""
import os, re, shlex, subprocess, sys
from pathlib import Path

def credentials():
    user=os.environ['OPS_USER'];host=os.environ['OPS_HOST']
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*',user):raise ValueError('Invalid SSH username')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*',host):raise ValueError('Invalid SSH hostname/address')
    return {'USERNAME':user,'HOST':host}

def ssh_args():
    c=credentials()
    return ['ssh','-i',os.environ['OPS_HOST_KEY'],'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+os.environ['OPS_HOST_KNOWN_HOSTS'],'-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',c['USERNAME']+'@'+c['HOST']]

if __name__=='__main__':
    script=sys.stdin.read()
    command='sudo -n bash -s' if '--sudo' in sys.argv else 'bash -s'
    p=subprocess.run(ssh_args()+[command],input=script,text=True,capture_output=True)
    sys.stdout.write(p.stdout);sys.stderr.write(p.stderr);raise SystemExit(p.returncode)
