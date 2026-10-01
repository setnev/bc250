"""Use real HTTP requests to verify failure injection and released request state."""
import threading,json,urllib.request,urllib.error
from pathlib import Path
from fault_proxy import Server
class Backend(__import__('http.server',fromlist=['BaseHTTPRequestHandler']).BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  self.rfile.read(int(self.headers['Content-Length']));self.send_response(200);self.end_headers();self.wfile.write(b'{"fixture_backend":true}')
import http.server
backend=http.server.ThreadingHTTPServer(('127.0.0.1',0),Backend)
proxy=Server(0,'http://127.0.0.1:'+str(backend.server_port))
for s in (backend,proxy):threading.Thread(target=s.serve_forever,daemon=True).start()
base='http://127.0.0.1:'+str(proxy.server_port);rows=[]
try:
 for variant,expected in [(0,[503,200,200]),(1,[200,503,200]),(2,[503,503,503])]:
  task='fixture-'+str(variant)
  req=urllib.request.Request(base+'/register',data=json.dumps({'task':task,'variant':variant}).encode(),headers={'Content-Type':'application/json'})
  urllib.request.urlopen(req,timeout=5).close();observed=[]
  for _ in range(3):
   req=urllib.request.Request(base+'/v1/chat/completions',data=b'{}',headers={'Content-Type':'application/json','X-Ops-Task':task})
   try:
    with urllib.request.urlopen(req,timeout=5) as response:response.read();observed.append(response.status)
   except urllib.error.HTTPError as e:e.read();observed.append(e.code)
  with urllib.request.urlopen(base+'/state/'+task,timeout=5) as response:state=json.load(response)
  assert observed==expected and state['active']==0,(observed,state)
  rows.append({'variant':variant,'actual_http_codes':observed,'request_state_released':True,'fault_count':state['faults']})
 Path(__file__).with_name('api-fault-validation.json').write_text(json.dumps({'case':'F05','apparatus_passed':True,'variants':rows,'scope':'Real proxy HTTP503 behavior; deterministic backend used only for apparatus check'},indent=2)+'\n')
 print(json.dumps(rows))
finally:
 for s in (proxy,backend):s.shutdown();s.server_close()
