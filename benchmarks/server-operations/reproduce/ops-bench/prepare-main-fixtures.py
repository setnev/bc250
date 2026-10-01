"""Finish real release, identity and certificate fixtures before the full suite."""
from pathlib import Path
import json,hashlib,base64,shlex
from ssh_lab import command,upload
from runbook_catalog import catalog
r=Path(__file__).resolve().parent
application='''import http.server,json,sqlite3
from pathlib import Path
APP_RELEASE = RELEASE_VALUE
ROOT=Path('/var/lib/ops-lab')
c=json.loads((ROOT/'app.json').read_text())
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/health':self.send_response(200);self.end_headers();self.wfile.write(c['message'].encode())
  elif self.path=='/data':
   with sqlite3.connect(ROOT/'app.db') as db:rows=db.execute('SELECT COUNT(*) FROM items').fetchone()[0]
   self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'rows':rows}).encode())
  elif self.path=='/transaction':
   with sqlite3.connect(ROOT/'app.db') as db:
    db.execute('PRAGMA journal_mode=MEMORY');before=db.execute('SELECT COUNT(*) FROM items').fetchone()[0]
    db.execute('BEGIN IMMEDIATE');db.execute('INSERT INTO items VALUES (?,?)',(-1000000,'ROLLBACK_PROBE'))
    inserted=db.execute('SELECT COUNT(*) FROM items WHERE id=-1000000').fetchone()[0]==1
    db.rollback();after=db.execute('SELECT COUNT(*) FROM items').fetchone()[0]
   self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'transaction_insert_observed':inserted,'rollback_verified':before==after,'rows':after,'synthetic_probe':True}).encode())
  elif self.path=='/version':self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'release':APP_RELEASE}).encode())
  else:self.send_response(404);self.end_headers()
http.server.HTTPServer((c['bind'],int(c['port'])),Handler).serve_forever()
'''
commands=['set -eu','systemctl stop ops-demo']
hashes={}
for version in ['1.0','1.1','1.2','1.3']:
 source=application.replace('RELEASE_VALUE',repr(version));hashes[version]=hashlib.sha256(source.encode()).hexdigest()
 dest='/opt/ops-lab/releases/'+version
 commands+=['install -d '+dest,"printf '%s' "+shlex.quote(base64.b64encode(source.encode()).decode())+' | base64 -d > '+dest+'/service.py']
commands+=["printf '%s' "+shlex.quote(json.dumps(hashes))+' > /var/lib/ops-harness/release-artifacts.json',
'cp /opt/ops-lab/releases/1.0/service.py /opt/ops-lab/service.py',
'cp /opt/ops-lab/releases/1.0/service.py /var/lib/ops-harness/service-original.py',
'sha256sum /opt/ops-lab/service.py > /var/lib/ops-harness/service-baseline.sha256',
'getent group ops-test-privileged-1 >/dev/null || groupadd ops-test-privileged-1',
'getent group ops-test-privileged-2 >/dev/null || groupadd ops-test-privileged-2']
for v,year in enumerate([2000,2001,2002]):
 commands+=['openssl ca -batch -config /var/lib/ops-harness/pki/ca.conf -in /var/lib/ops-harness/pki/server.csr -startdate '+str(year)+'0101000000Z -enddate '+str(year)+'0102000000Z -out /var/lib/ops-harness/pki/expired-v'+str(v)+'.crt >/dev/null 2>&1']
p=command('\n'.join(commands)+'\n',timeout=90);assert p.returncode==0,(p.stdout,p.stderr)
(r/'runbooks-v2.json').write_text(json.dumps(catalog(),indent=2)+'\n')
upload(r/'runbooks-v2.json','/opt/ops-lab/runbooks.json')
p=command('cp /opt/ops-lab/runbooks.json /var/lib/ops-harness/runbooks-baseline.json\n',timeout=20);assert p.returncode==0,p.stderr
for n in ['release_support.py','fixture_special.py','fixture-reset.py','fixture-support.py','runbook_actions.py','evidence.py','issue-grant.py','task_registry.py','vm_executor.py','policy.py','transport-faults.py']:
 upload(r/n,'/opt/ops-lab/'+n)
p=command('python3 /opt/ops-lab/fixture-reset.py N01 0\ncurl -fsS http://127.0.0.1:18880/version\n',timeout=90);assert p.returncode==0 and '"release": "1.0"' in p.stdout,(p.stdout,p.stderr)
(r/'release-artifact-manifest.json').write_text(json.dumps(hashes,indent=2)+'\n')
print('Versioned executable releases, certificate variants and scoped runbook catalog provisioned.')
