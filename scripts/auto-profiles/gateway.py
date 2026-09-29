#!/usr/bin/env python3
"""Authenticated streaming API gateway with serialized model/profile transitions."""
import hmac,http.client,http.server,json,os,pathlib,socket,threading,time
CFG=json.loads(pathlib.Path(os.environ.get('BC250_GATEWAY_CONFIG','/etc/bc250-ai/gateway.json')).read_text())
KEY=pathlib.Path(CFG['key_file']).read_text().strip()
GATE=threading.Lock();active=None;last_used=time.monotonic()
def control(op,model=None):
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.settimeout(100);s.connect(CFG['socket']);s.sendall(json.dumps({'op':op,'model':model}).encode()+b'\n')
  with s.makefile('rb') as f:r=json.loads(f.readline(16384))
 if not r.get('ok'):raise RuntimeError(r.get('error','Profile controller unavailable'))
 return r['state']
class ModelBusy(RuntimeError):pass
def connection():return http.client.HTTPConnection(CFG['backend_host'],CFG['backend_port'],timeout=600)
def backend(path,payload=None):
 c=connection()
 try:
  c.request('GET' if payload is None else 'POST',path,body=None if payload is None else json.dumps(payload).encode(),headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json'})
  r=c.getresponse();body=r.read()
  if r.status==500 and b'model limit reached' in body:raise ModelBusy('Previous worker is still being reaped')
  if r.status>=400:raise RuntimeError('Backend management request failed: '+str(r.status))
  return json.loads(body)
 finally:c.close()
def workers_alive():
 # The router's unload acknowledgment can precede child-process exit.
 workers=set()
 for p in pathlib.Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   if p.stat().st_uid!=os.geteuid():continue
   args=(p/'cmdline').read_bytes().split(b'\0')
   if args and args[0].endswith(b'llama-server') and b'--models-preset' not in args and b'--models-dir' not in args:workers.add(int(p.name))
  except (OSError,PermissionError):continue
 return workers

def unload():
 global active
 # Reconcile after gateway/backend restarts instead of trusting only local state.
 old_workers=workers_alive()
 models=backend('/models').get('data',[])
 for m in models:
  status=m.get('status',{})
  if (status.get('value') if isinstance(status,dict) else status) in ('loaded','loading','sleeping'):
   backend('/models/unload',{'model':m['id']})
 deadline=time.monotonic()+30
 while old_workers & workers_alive():
  if time.monotonic()>deadline:raise RuntimeError('Previous worker did not exit')
  time.sleep(.1)
 active=None

def ensure(model):
 global active
 if active!=model:unload()
 profile=control('apply',model)
 catalog=backend('/models').get('data',[])
 status=next((m.get('status',{}).get('value') for m in catalog if m['id']==model),None)
 if status!='loaded':
  deadline=time.monotonic()+10
  while True:
   try:backend('/models/load',{'model':model});break
   except ModelBusy:
    if time.monotonic()>deadline:raise
    time.sleep(.25)
 deadline=time.monotonic()+180
 while True:
  status=next((m.get('status',{}).get('value') for m in backend('/models').get('data',[]) if m['id']==model),None)
  if status=='loaded':break
  if status not in ('loading','sleeping') or time.monotonic()>deadline:raise RuntimeError('Model did not become ready')
  time.sleep(.25)
 active=model
 return profile

def idle():
 global last_used
 while True:
  time.sleep(1)
  if time.monotonic()-last_used<CFG.get('idle_seconds',60):continue
  if GATE.acquire(blocking=False):
   try:
    if active is not None and time.monotonic()-last_used>=CFG.get('idle_seconds',60):unload();control('idle')
   except Exception:pass
   finally:GATE.release()

class Handler(http.server.BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args):pass # Never log client addresses or prompts.
 def reply(self,status,obj):
  b=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.send_header('Connection','close');self.end_headers();self.wfile.write(b);self.close_connection=True
 def authenticated(self):
  if hmac.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+KEY).encode()):return True
  self.reply(401,{'error':{'message':'Invalid API key'}});return False
 def do_GET(self):
  if self.path=='/health':
   try:
    state=control('status');backend('/health');self.reply(503 if state.get('latched') else 200,{'status':'unavailable' if state.get('latched') else 'ok'})
   except Exception:self.reply(503,{'status':'unavailable'})
   return
  if not self.authenticated():return
  if self.path in ('/models','/v1/models'):
   self.reply(200,{'object':'list','data':[{'id':name,'object':'model','owned_by':'local'} for name in CFG['models']]})
  elif self.path=='/v1/hardware':
   try:self.reply(200,control('status'))
   except Exception:self.reply(503,{'error':{'message':'Profile controller unavailable'}})
  else:self.reply(404,{'error':{'message':'Unknown endpoint'}})
 def do_POST(self):
  global active,last_used
  if not self.authenticated():return
  if self.path not in ('/v1/chat/completions','/chat/completions','/v1/completions','/completion','/v1/embeddings','/embeddings','/v1/responses','/models/load','/models/unload'):
   self.reply(404,{'error':{'message':'Unknown endpoint'}});return
  try:
   if self.headers.get('Transfer-Encoding'):raise ValueError('Use Content-Length')
   n=int(self.headers.get('Content-Length','0'))
   if n<=0 or n>16*1024**2:raise ValueError('Invalid request size')
   self.connection.settimeout(30);body=self.rfile.read(n)
   if len(body)!=n:raise ValueError('Incomplete body')
   payload=json.loads(body);model=payload.get('model')
   if payload.get('background'):raise ValueError('Background inference is not supported')
   if model not in CFG['models']:raise ValueError('Unknown or missing model')
  except (ValueError,AttributeError,TypeError):self.reply(400,{'error':{'message':'Invalid request or model'}});return
  if not GATE.acquire(timeout=120):self.reply(503,{'error':{'message':'Inference queue is busy'}});return
  sent=False;c=None
  try:
   if self.path=='/models/unload':
    if active==model:unload();control('idle')
    self.reply(200,{'success':True});return
   profile=ensure(model)
   if self.path=='/models/load':self.reply(200,{'success':True,'profile':profile['profile']});return
   c=connection();c.request('POST',self.path,body=body,headers={'Content-Type':'application/json','Authorization':'Bearer '+KEY})
   r=c.getresponse();self.send_response(r.status);self.send_header('Content-Type',r.getheader('Content-Type','application/json'));self.send_header('Transfer-Encoding','chunked');self.send_header('Connection','close');self.send_header('X-BC250-Profile',profile['profile']);self.send_header('X-BC250-Clock-MHz',str(profile['actual']['gfx_frequency_mhz']));self.send_header('X-BC250-Voltage-mV',str(profile['actual']['gfx_voltage_mv']));self.end_headers();sent=True
   disconnected=False
   while True:
    chunk=r.read1(65536)
    if not chunk:break
    if not disconnected:
     try:self.wfile.write(('%X\r\n'%len(chunk)).encode()+chunk+b'\r\n');self.wfile.flush()
     except (BrokenPipeError,ConnectionResetError,socket.timeout):disconnected=True
   # Drain a disconnected client's entire upstream response before releasing the lock.
   if not disconnected:self.wfile.write(b'0\r\n\r\n');self.wfile.flush()
  except Exception:
   # On uncertain completion, stop the backend before another profile may be applied.
   try:control('abort')
   except Exception:pass
   active=None
   if not sent:
    try:self.reply(503,{'error':{'message':'Inference unavailable; hardware profile or backend check failed'}})
    except OSError:pass
  finally:
   if c:c.close()
   last_used=time.monotonic();self.close_connection=True;GATE.release()

class Server(http.server.ThreadingHTTPServer):
 daemon_threads=True
 request_queue_size=32

def main():
 with GATE:
  deadline=time.monotonic()+60
  while True:
   try:unload();control('idle');break
   except (OSError,RuntimeError):
    if time.monotonic()>deadline:raise
    time.sleep(1)
 threading.Thread(target=idle,daemon=True).start()
 Server((CFG['listen_host'],CFG['listen_port']),Handler).serve_forever()
if __name__=='__main__':main()
