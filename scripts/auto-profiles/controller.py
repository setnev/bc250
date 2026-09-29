#!/usr/bin/env python3
"""Root-owned, local-only named GPU profile controller; no client-supplied clocks."""
import json,os,pathlib,pwd,signal,socket,socketserver,struct,subprocess,sys,threading,time
CONFIG=pathlib.Path(os.environ.get('BC250_PROFILE_CONFIG','/etc/bc250-ai/profiles.json'))
CFG=json.loads(CONFIG.read_text());CONTROL=CFG['clock_control'];SOCKET=CFG['socket']
cpu=None
lock=threading.RLock();state={'profile':None,'model':None,'latched':False};done=threading.Event()
def clock(*args):return json.loads(subprocess.check_output(['/usr/bin/python3',CONTROL,*map(str,args)],text=True,timeout=5))
def temperature():
 paths=list(pathlib.Path('/sys/class/drm').glob('card*/device/hwmon/hwmon*/temp1_input'))
 if not paths:raise RuntimeError('GPU temperature sensor missing')
 return max(int(p.read_text()) for p in paths)/1000

def apply(name,model=None):
 target=CFG['profiles'][name]
 actual=clock('set',target['mhz'],target['vid'])
 if actual['gfx_frequency_mhz']!=target['mhz'] or actual['gfx_vid']!=target['vid']:raise RuntimeError('Clock/voltage readback mismatch')
 state.update(profile=name,model=model,actual=actual)
 print(json.dumps({'event':'profile','profile':name,'model':model,'actual':actual}),flush=True)
 return actual

def stop_backend():
 subprocess.run(['systemctl','stop','bc250-ai.service'],check=True,timeout=45)

def trip(reason):
 state.update(latched=True,error=reason)
 try:
  if cpu:cpu.idle()
 finally:
  try:apply('idle')
  finally:stop_backend()
 print(json.dumps({'event':'latched','reason':reason}),flush=True)

def dispatch(request):
 with lock:
  op=request.get('op')
  if op=='status':return {**state,'temperature_c':temperature(),'cpu':cpu.status() if cpu else None}
  if op=='cpu_idle':
   if cpu:cpu.idle()
   return dict(state)
  if op=='cpu_active':
   if state['latched']:raise RuntimeError('Hardware guard latched')
   if cpu:cpu.boost()
   return dict(state)
  if op=='abort':
   try:
    try:
     if cpu:cpu.idle()
    finally:
     try:apply('idle')
     finally:stop_backend()
   except Exception:
    state['latched']=True;raise
   if not state['latched']:subprocess.run(['systemctl','start','bc250-ai.service'],check=True,timeout=45)
   return dict(state)
  if op not in ('apply','idle'):raise ValueError('Unsupported operation')
  if state['latched']:raise RuntimeError('Thermal/hardware guard latched; operator review required')
  if temperature()>=CFG['cutoff_c']:
   trip('temperature cutoff');raise RuntimeError('Temperature cutoff')
  if op=='idle':
   if cpu:cpu.idle()
   apply('idle')
  else:
   model=request.get('model')
   if model not in CFG['models']:raise ValueError('Unknown model')
   profile=CFG['models'][model]
   if state['profile']!=profile or state['model']!=model:apply(profile,model)
   else:
    actual=clock();target=CFG['profiles'][profile]
    if actual['gfx_frequency_mhz']!=target['mhz'] or actual['gfx_vid']!=target['vid']:
     trip('external clock/voltage change');raise RuntimeError('Clock changed')
  return dict(state)

class Handler(socketserver.StreamRequestHandler):
 def handle(self):
  self.request.settimeout(60)
  _,uid,_=struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
  try:
   if uid not in (0,pwd.getpwnam(CFG['client_user']).pw_uid):raise PermissionError('Peer denied')
   line=self.rfile.readline(4097)
   if len(line)>4096:raise ValueError('Request too large')
   result={'ok':True,'state':dispatch(json.loads(line))}
  except Exception as e:result={'ok':False,'error':str(e)}
  self.wfile.write(json.dumps(result).encode()+b'\n')
class Server(socketserver.ThreadingUnixStreamServer):
 daemon_threads=True

def guard():
 ticks=0
 while not done.wait(.5):
  with lock:
   if state['latched']:continue
   try:
    if cpu:cpu.expire()
    if temperature()>=CFG['cutoff_c']:trip('temperature cutoff')
    elif ticks%20==0 and state['profile']:
     a=clock();t=CFG['profiles'][state['profile']]
     if a['gfx_frequency_mhz']!=t['mhz'] or a['gfx_vid']!=t['vid']:trip('external clock/voltage change')
   except Exception as e:
    try:trip(type(e).__name__)
    except Exception:state['latched']=True
   ticks+=1

def main():
 global cpu
 from cpu_power import CpuPower
 cpu=CpuPower()
 if pathlib.Path(SOCKET).exists():pathlib.Path(SOCKET).unlink()
 server=Server(SOCKET,Handler);os.chown(SOCKET,0,pwd.getpwnam(CFG['client_user']).pw_gid);os.chmod(SOCKET,0o660)
 apply('idle');threading.Thread(target=guard,daemon=True).start()
 def shutdown(*_):threading.Thread(target=server.shutdown,daemon=True).start()
 signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
 try:server.serve_forever(poll_interval=.5)
 finally:
  done.set();server.server_close()
  with lock:
   if cpu:cpu.restore()
   clock('restore')
if __name__=='__main__':main()
