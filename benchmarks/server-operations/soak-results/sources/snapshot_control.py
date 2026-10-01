"""Private host-side QMP snapshots; never expose this control to agents."""
from pathlib import Path
import subprocess,json,time
ROOT=Path(__file__).resolve().parent
LABEL='ops-main-v5'
def qmp(operation):
 if operation not in ['savevm','loadvm','info snapshots']:raise ValueError('Unknown snapshot operation')
 script='''import socket,json,time
from pathlib import Path
p=Path('/opt/bc250-mod-prep/ops-bench/lab/qmp.sock')
s=socket.socket(socket.AF_UNIX);s.settimeout(90);s.connect(str(p));f=s.makefile('rwb')
json.loads(f.readline())
def call(name,args=None):
 f.write((json.dumps({'execute':name,**({'arguments':args} if args else {})})+'\\n').encode());f.flush()
 while True:
  v=json.loads(f.readline())
  if 'error' in v:raise RuntimeError(v['error'])
  if 'return' in v:return v['return']
call('qmp_capabilities')
result=call('human-monitor-command',{'command-line':COMMAND})
if result and ('Error' in result or 'failed' in result.lower()):raise RuntimeError(result)
print(json.dumps({'operation':COMMAND,'result':result,'host_epoch':time.time()}))
'''.replace('COMMAND',repr(operation if operation=='info snapshots' else operation+' '+LABEL))
 p=subprocess.run(['python3',str(ROOT.parent/'remote.py'),'--sudo'],input="python3 - <<'PY'\n"+script+"\nPY\n",capture_output=True,text=True,timeout=110)
 if p.returncode:raise RuntimeError('Snapshot control failed: '+p.stderr[-2000:])
 return json.loads(p.stdout.strip().splitlines()[-1])
def restore():
 from ssh_lab import command
 start=time.monotonic();result=qmp('loadvm');last=None
 for _ in range(25):
  try:
   p=command('date -u -s @'+str(int(time.time()))+' >/dev/null\ntest "$(hostname)" = ops-lab\ntest "$(cat /var/lib/ops-harness/main-snapshot-marker)" = ops-main-v5\ncurl -fsS --max-time 2 http://127.0.0.1:18880/health\n',timeout=8)
   if p.returncode==0 and p.stdout.strip()=='OPS_LAB_V0_OK':return {**result,'pinned_ssh_healthy':True,'snapshot_health_verified':True,'seconds':time.monotonic()-start}
   last=p.stderr[-500:]
  except subprocess.TimeoutExpired:last='Pinned SSH reconnect timeout'
  time.sleep(.2)
 raise RuntimeError('Snapshot restore failed independent health verification: '+str(last))
if __name__=='__main__':
 import sys
 print(json.dumps(restore() if sys.argv[1]=='restore' else qmp(sys.argv[1])))
