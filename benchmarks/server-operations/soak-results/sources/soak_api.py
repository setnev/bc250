"""Private authenticated production transport for the separately profiled soak."""
from pathlib import Path
import http.server, json, threading, time, urllib.request, urllib.error

CONFIG = dict(line.split('=',1) for line in Path(__file__).resolve().parent.parent.joinpath('client.env').read_text().splitlines() if '=' in line)
BASE = CONFIG['BC250_BASE_URL'].rstrip('/')
AUTH = {'Authorization':'Bearer '+CONFIG['BC250_API_KEY']}

def request(path, payload=None, timeout=180):
    req=urllib.request.Request(BASE+path, data=json.dumps(payload).encode() if payload is not None else None, headers={**AUTH,'Content-Type':'application/json'})
    return urllib.request.urlopen(req,timeout=timeout)

def json_request(path, payload=None, timeout=30):
    with request(path,payload,timeout) as response:return json.load(response)

def api(payload,budget,task=None,fault=False):
    payload={**payload,'stream':True,'stream_options':{'include_usage':True}}
    start=time.monotonic();first=None;content='';calls={};usage=None;timings=None;finish=None
    if fault:
        req=urllib.request.Request('http://127.0.0.1:18121/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Ops-Task':task})
        response=urllib.request.urlopen(req,timeout=max(1,min(120,budget)))
    else:response=request('/chat/completions',payload,max(1,min(120,budget)))
    with response:
        for raw in response:
            if time.monotonic()-start>budget:raise TimeoutError('Case deadline during inference')
            line=raw.decode().strip()
            if not line.startswith('data: '):continue
            if line=='data: [DONE]':break
            value=json.loads(line[6:]);usage=value.get('usage') or usage;timings=value.get('timings') or timings
            for choice in value.get('choices',[]):
                delta=choice.get('delta',{});finish=choice.get('finish_reason') or finish
                if first is None and (delta.get('content') or delta.get('tool_calls')):first=time.monotonic()-start
                content+=delta.get('content') or ''
                for call in delta.get('tool_calls',[]):
                    entry=calls.setdefault(call['index'],{'id':'','type':'function','function':{'name':'','arguments':''}})
                    if call.get('id'):entry['id']=call['id']
                    function=call.get('function',{});entry['function']['name']+=function.get('name') or '';entry['function']['arguments']+=function.get('arguments') or ''
    message={'role':'assistant','content':content or None}
    if calls:message['tool_calls']=[calls[key] for key in sorted(calls)]
    return message,{'seconds':time.monotonic()-start,'first_content_or_tool_delta_seconds':first,'usage':usage,'timings':timings,'finish_reason':finish}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0'))
        if self.path!='/v1/chat/completions' or not 0<n<=1024**2:
            self.send_error(400);return
        try:
            payload=json.loads(self.rfile.read(n))
            with request('/chat/completions',payload,120) as upstream:
                self.send_response(upstream.status);self.send_header('Content-Type',upstream.headers.get('Content-Type','application/json'));self.send_header('Connection','close');self.end_headers()
                while True:
                    chunk=upstream.read1(4096)
                    if not chunk:break
                    self.wfile.write(chunk);self.wfile.flush()
        except urllib.error.HTTPError as error:
            self.send_error(error.code)
        except (BrokenPipeError,ConnectionResetError):pass
        finally:self.close_connection=True

def forwarding_server():
    server=http.server.ThreadingHTTPServer(('127.0.0.1',18123),Handler)
    server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server
