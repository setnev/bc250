"""Root-owned test credentials used only by authentication probes in the guest."""
from pathlib import Path
import subprocess,json,secrets,time,http.server,urllib.request,urllib.error
PRIVATE=Path('/var/lib/ops-harness/identity');ROOT=Path('/var/lib/ops-lab')
def install_key(which):
 p=Path('/home/ops-test-account/.ssh/authorized_keys')
 p.write_text('restrict,command="/usr/bin/true" '+(PRIVATE/(which+'.pub')).read_text())
 subprocess.run(['chown','ops-test-account:ops-test-account',str(p)],check=True);p.chmod(0o600)
def ssh_probe(which,user='ops-test-account'):
 p=subprocess.run(['ssh','-i',str(PRIVATE/which),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(PRIVATE/'known_hosts'),'-o','ConnectTimeout=3',user+'@127.0.0.1','true'],capture_output=True,timeout=8)
 return p.returncode==0
def token_probe(token):
 try:
  r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18884/auth',headers={'Authorization':'Bearer '+token}),timeout=3)
  return r.status
 except urllib.error.HTTPError as e:return e.code
def identities():
 data=json.loads((PRIVATE/'tokens.json').read_text())
 return {'old_ssh_authenticates':ssh_probe('old'),'new_ssh_authenticates':ssh_probe('new'),
         'old_token_status':token_probe(data['old']),'replacement_token_status':token_probe(data['new'])}
def reset(variant=0):
 import shutil
 for name in ['old','new','unexpected']:
  for ext in ['','.pub']:
   src=PRIVATE/(name+'-v'+str(variant)+ext)
   if src.exists():shutil.copy2(src,PRIVATE/(name+ext))
 install_key('old')
 data={'old':secrets.token_hex(24),'new':secrets.token_hex(24)}
 (PRIVATE/'tokens.json').write_text(json.dumps(data));(PRIVATE/'tokens.json').chmod(0o600)
 (PRIVATE/'active-token').write_text(data['old']);(PRIVATE/'active-token').chmod(0o600)
def serve():
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   good=self.path=='/auth' and secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+(PRIVATE/'active-token').read_text())
   self.send_response(200 if good else 401);self.end_headers();self.wfile.write(b'authorized\n' if good else b'denied\n')
 http.server.HTTPServer(('127.0.0.1',18884),Handler).serve_forever()
if __name__=='__main__':
 import sys
 if sys.argv[1]=='serve':serve()
 elif sys.argv[1]=='reset':reset(int(sys.argv[2]) if len(sys.argv)>2 else 0)
 elif sys.argv[1]=='probe':print(json.dumps(identities()))
