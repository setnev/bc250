"""Controller fault injection: live SSH worker death, lease expiry and host QoS."""
from pathlib import Path
import subprocess,json,time,os,signal,shlex
from ssh_lab import command,ssh_args
ROOT=Path(__file__).resolve().parent
def inject(task):
 child=subprocess.Popen(ssh_args(executor=True),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 child.stdin.write(json.dumps({'name':'inspect','task_id':task['task_id'],'arguments':{'target':'lab-01','resource':'app_logs'}})+'\n');child.stdin.close();start=time.monotonic()
 try:
  for _ in range(10):
   p=command('test -f /var/lib/ops-harness/f08-active-reader\n')
   if p.returncode==0:break
   if child.poll() is not None:raise RuntimeError('Injected SSH worker ended before crash')
   time.sleep(.1)
  else:raise RuntimeError('SSH worker never held an active operation')
  p=subprocess.run(['python3',str(ROOT.parent/'remote.py'),'--sudo'],input='python3 /opt/bc250-mod-prep/ops-bench/lease-fixture.py\n',capture_output=True,text=True,timeout=15)
  if p.returncode:raise RuntimeError('Host CPU latency crash fixture failed: '+p.stderr)
  qos=json.loads(p.stdout.strip().splitlines()[-1]);assert qos['power_constraint_released'],qos
  os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
  while time.monotonic()-start<25:
   p=command('test ! -f /var/lib/ops-harness/f08-active-reader\n')
   if p.returncode==0:break
   time.sleep(.5)
  else:raise RuntimeError('Remote worker operation did not close within timeout')
  p=command('python3 /opt/ops-lab/issue-grant.py deploy_release '+shlex.quote(json.dumps({'message':task['desired_message']}))+' '+shlex.quote(task['task_id'])+'\n')
  if p.returncode==0:raise RuntimeError('Expired lease still allowed a replacement write grant')
  return {'actual_ssh_worker_crashed':child.returncode<0,'remote_operation_closed':True,'expired_authorization_denied':True,'host_cpu_qos':qos,'fault_cleanup_seconds':time.monotonic()-start}
 finally:
  if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
