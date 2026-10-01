"""Reversible inference maintenance window with a hardware guard and deadline."""
from pathlib import Path
import subprocess,json,time,threading,signal,os,sys,urllib.request,uuid
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'window';OUT.mkdir(exist_ok=True)
services=['bc250-profile-controller.service','bc250-ai.service','bc250-api-gateway.service']
state=ROOT/'restore-state.json';child=None;fault=None;stop=threading.Event()
vm_pid=int(subprocess.check_output(['systemctl','show','bc250-ops-lab.service','-p','MainPID','--value'],text=True).strip())
assert vm_pid>0 and b'restrict=on' in Path(f'/proc/{vm_pid}/cmdline').read_bytes(),'Lab containment is unavailable'
epoch_start=time.time();window_id=uuid.uuid4().hex
(OUT/'start.json').write_text(json.dumps({'window_id':window_id,'started_epoch':epoch_start,'vm_pid':vm_pid}))
def terminate():
 if child and child.poll() is None:
  os.killpg(child.pid,signal.SIGTERM)
def guard():
 global fault
 sensors=list(Path('/sys/class/drm').glob('card*/device/hwmon/hwmon*/temp1_input'));low_since=None;next_kernel_check=0
 with (OUT/'telemetry.jsonl').open('a') as f:
  while not stop.wait(.5):
   try:
    if not sensors:raise RuntimeError('Temperature telemetry unavailable')
    edge=max(int(p.read_text())/1000 for p in sensors)
    if not 0<edge<120:raise RuntimeError('Temperature telemetry invalid')
    mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
    f.write(json.dumps({'window_id':window_id,'epoch':time.time(),'edge_c':edge,'available_bytes':mem})+'\n');f.flush()
    if edge>=85:raise RuntimeError('GPU edge reached 85 C')
    if mem<512*1024**2:
     low_since=low_since or time.monotonic()
     if time.monotonic()-low_since>=5:raise RuntimeError('512 MiB memory reserve exhausted')
    else:low_since=None
    if time.monotonic()>next_kernel_check:
     next_kernel_check=time.monotonic()+5
     current=int(subprocess.check_output(['systemctl','show','bc250-ops-lab.service','-p','MainPID','--value'],text=True).strip())
     if current!=vm_pid:raise RuntimeError('Lab VM host process changed unexpectedly')
     events=subprocess.run(['journalctl','-k','--since','@'+str(int(epoch_start)),'--grep','amdgpu.*(reset|fault)|GPU hang|Out of memory|oom-kill','-o','cat','--no-pager','-n','1'],text=True,capture_output=True,timeout=3)
     if events.returncode==0 and events.stdout.strip() and events.stdout.strip()!='-- No entries --':raise RuntimeError('Host GPU fault or OOM event detected')
   except Exception as e:fault=str(e);terminate();return
def signal_handler(signum,frame):stop.set();terminate()
for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,signal_handler)
assert not state.exists(),'A previous restoration is pending'
govs={str(p):p.read_text().strip() for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_governor')}
active=[s for s in services if subprocess.run(['systemctl','is-active','--quiet',s]).returncode==0]
state.write_text(json.dumps({'cpu_governors':govs,'services':active},indent=2));state.chmod(0o600)
thread=threading.Thread(target=guard,daemon=True)
try:
 subprocess.run(['systemctl','stop',*services],check=True)
 for p in govs:Path(p).write_text('performance')
 applied=json.loads(subprocess.check_output(['python3','/usr/local/libexec/bc250-profile-clock.py','set','1700','100'],text=True))
 assert applied['gfx_frequency_mhz']==1700 and applied['gfx_vid']==100,applied
 (OUT/('clock-'+window_id+'.json')).write_text(json.dumps(applied,indent=2))
 thread.start()
 args=['/opt/bc250-ai/llama.cpp/build/bin/llama-server','--models-preset',str(ROOT/'models.ini'),'--models-max','1','--host','127.0.0.1','--port','18220']
 with (OUT/('router-'+window_id+'.log')).open('w') as log:
  child=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  deadline=time.monotonic()+10800
  while child.poll() is None and not stop.wait(.5):
   if time.monotonic()>deadline:fault='Three-hour maintenance window expired';terminate();break
  if child.poll() is None:
   try:child.wait(timeout=15)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
  if child.returncode and not stop.is_set() and not fault:fault='Inference router exited unexpectedly'
finally:
 stop.set();terminate()
 if child and child.poll() is None:
  try:child.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
 if thread.is_alive():thread.join(timeout=2)
 subprocess.run(['python3',str(ROOT/'restore.py')],check=True)
 (OUT/'completion.json').write_text(json.dumps({'window_id':window_id,'started_epoch':epoch_start,'guard_fault':fault,'production_restore_invoked':True,'finished_epoch':time.time()},indent=2))
 if fault:raise RuntimeError(fault)
