#!/usr/bin/env python3
"""Request-scoped CPU boost, idle schedutil, and crash-safe QoS lifetime."""
import json,os,pathlib,struct,time

class CpuPower:
 def __init__(self,root='/sys/devices/system/cpu/cpufreq',saved='/run/bc250-profile/cpu-original.json',qos='/dev/cpu_dma_latency'):
  self.policies=sorted(pathlib.Path(root).glob('policy*'));self.saved=pathlib.Path(saved);self.qos=qos;self.fd=None;self.mode='uninitialized';self.deadline=0
  if not self.policies:raise RuntimeError('CPU frequency policies missing')
  for p in self.policies:
   available=(p/'scaling_available_governors').read_text().split()
   if not {'schedutil','performance'}<=set(available):raise RuntimeError('Required CPU governors missing')
  if not self.saved.exists():
   self.saved.write_text(json.dumps({str(p/'scaling_governor'):(p/'scaling_governor').read_text().strip() for p in self.policies}))
  self.idle()
 def idle(self):
  if self.fd is not None:os.close(self.fd);self.fd=None
  for p in self.policies:(p/'scaling_governor').write_text('schedutil')
  self.mode='idle';self.deadline=0
 def boost(self):
  if self.mode!='active':
   try:
    self.fd=os.open(self.qos,os.O_WRONLY);os.write(self.fd,struct.pack('i',100))
    for p in self.policies:(p/'scaling_governor').write_text('performance')
   except Exception:self.idle();raise
   self.mode='active'
  self.deadline=time.monotonic()+90
 def expire(self):
  if self.mode=='active' and time.monotonic()>self.deadline:self.idle()
 def status(self):return {'mode':self.mode,'governor':'performance' if self.mode=='active' else 'schedutil','latency_request_us':100 if self.fd is not None else None,'lease_remaining_s':max(0,round(self.deadline-time.monotonic(),1))}
 def restore(self):
  if self.fd is not None:os.close(self.fd);self.fd=None
  restore(self.saved)

def restore(saved=pathlib.Path('/run/bc250-profile/cpu-original.json')):
 saved=pathlib.Path(saved)
 if saved.exists():
  for path,value in json.loads(saved.read_text()).items():pathlib.Path(path).write_text(value)
  saved.unlink()
if __name__=='__main__':restore()
