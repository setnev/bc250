"""Loopback-only inference fault injection with observable request cleanup."""
import http.server,json,urllib.request,urllib.error,threading
class State:
 def __init__(self):self.lock=threading.Lock();self.tasks={}
 def register(self,task,variant):
  if not isinstance(task,str) or variant not in (0,1,2):raise ValueError('Invalid fixture registration')
  with self.lock:self.tasks[task]={'variant':variant,'calls':0,'faults':0,'active':0}
 def begin(self,task):
  with self.lock:
   s=self.tasks[task];s['calls']+=1;s['active']+=1
   fault=s['calls'] <= (1 if s['variant']==0 else 2) or s['variant']==2
   if fault:s['faults']+=1
   return fault
 def end(self,task):
  with self.lock:self.tasks[task]['active']-=1
 def snapshot(self,task):
  with self.lock:return dict(self.tasks[task])
class Server(http.server.ThreadingHTTPServer):
 daemon_threads=True
 def __init__(self,port,backend):super().__init__(('127.0.0.1',port),Handler);self.backend=backend;self.state=State()
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send_json(self,status,data):
  raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  if not self.path.startswith('/state/'):return self.send_json(404,{'error':'Unknown route'})
  try:self.send_json(200,self.server.state.snapshot(self.path[7:]))
  except KeyError:self.send_json(404,{'error':'Unknown fixture'})
 def do_POST(self):
  n=int(self.headers.get('Content-Length','0'))
  if not 0<n<=1024**2:return self.send_json(413,{'error':'Request size exceeded'})
  raw=self.rfile.read(n)
  if self.path=='/register':
   try:
    v=json.loads(raw);self.server.state.register(v['task'],v['variant']);return self.send_json(200,{'registered':True})
   except Exception:return self.send_json(400,{'error':'Invalid registration'})
  if self.path!='/v1/chat/completions':return self.send_json(404,{'error':'Unknown route'})
  task=self.headers.get('X-Ops-Task','')
  try:fault=self.server.state.begin(task)
  except KeyError:return self.send_json(403,{'error':'Unregistered fixture'})
  try:
   if fault:return self.send_json(503,{'error':{'message':'Controlled inference unavailability','type':'fixture_failure'}})
   req=urllib.request.Request(self.server.backend+'/v1/chat/completions',data=raw,headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=120) as upstream:
    self.send_response(upstream.status);self.send_header('Content-Type',upstream.headers.get('Content-Type','application/json'));self.end_headers()
    while True:
     chunk=upstream.read1(4096)
     if not chunk:break
     self.wfile.write(chunk);self.wfile.flush()
  except urllib.error.HTTPError as e:
   try:self.send_json(e.code,{'error':'Backend HTTP failure'})
   except (BrokenPipeError,ConnectionResetError):pass
  except (BrokenPipeError,ConnectionResetError):pass
  finally:self.server.state.end(task)
if __name__=='__main__':Server(18121,'http://127.0.0.1:18120').serve_forever()
