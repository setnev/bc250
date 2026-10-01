"""Bounded real CPU latency request; kernel releases it when the worker exits."""
from pathlib import Path
import os,struct,subprocess,sys,time,json,signal
def read_qos():
 fd=os.open('/dev/cpu_dma_latency',os.O_RDONLY)
 try:return struct.unpack('i',os.read(fd,4))[0]
 finally:os.close(fd)
if len(sys.argv)>1 and sys.argv[1]=='worker':
 fd=os.open('/dev/cpu_dma_latency',os.O_RDWR);os.write(fd,struct.pack('i',0));print('lease-acquired',flush=True)
 time.sleep(30);os.close(fd);raise SystemExit()
before=read_qos();child=subprocess.Popen([sys.executable,__file__,'worker'],stdout=subprocess.PIPE,text=True,start_new_session=True)
try:
 assert child.stdout.readline().strip()=='lease-acquired'
 held=read_qos();assert held==0,held
 time.sleep(1)
 os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
 after=read_qos()
 print(json.dumps({'actual_cpu_dma_latency':True,'baseline_microseconds':before,'leased_microseconds':held,'restored_microseconds':after,'worker_crash_observed':child.returncode<0,'power_constraint_released':after==before}))
 assert after==before,'CPU latency constraint was not released'
finally:
 if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
