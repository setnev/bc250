"""Build a disposable Ubuntu VM. No model has shell or provisioning credentials."""
from pathlib import Path
import subprocess,json,yaml,hashlib
root=Path(__file__).resolve().parent
private=root.parent/'lab-private'
image='anthos-ops-qemu:20260930'
base='noble-server-cloudimg-amd64.img'
assert (root/base).is_file()
# Trusted initial provisioning, not the model execution network.
health='''import pathlib,json,http.server,sqlite3
root=pathlib.Path('/var/lib/ops-lab')
c=json.loads((root/'app.json').read_text())
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/health':
   self.send_response(200);self.end_headers();self.wfile.write(c['message'].encode())
  elif self.path=='/data':
   db=sqlite3.connect(root/'app.db');n=db.execute('SELECT count(*) FROM items').fetchone()[0];db.close()
   self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'rows':n}).encode())
  else:self.send_response(404);self.end_headers()
http.server.HTTPServer((c['bind'],int(c['port'])),Handler).serve_forever()
'''
unit='''[Unit]
Description=Disposable operations fixture
After=network.target
[Service]
User=opsapp
Group=opsapp
ExecStart=/usr/bin/python3 -u /opt/ops-lab/service.py
WorkingDirectory=/var/lib/ops-lab
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/ops-lab
Restart=no
[Install]
WantedBy=multi-user.target
'''
provision='''#!/bin/bash
set -euo pipefail
useradd --system --home /var/lib/ops-lab --shell /usr/sbin/nologin opsapp || true
install -d -m 755 -o opsapp -g opsapp /var/lib/ops-lab
printf '%s\\n' '{"bind":"0.0.0.0","port":18881,"message":"OPS_LAB_OK","release":"1.0"}' > /var/lib/ops-lab/app.json
python3 - <<'INNER'
import sqlite3,pathlib
p=pathlib.Path('/var/lib/ops-lab');d=sqlite3.connect(p/'app.db')
d.execute('CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, value TEXT)')
d.executemany('INSERT OR REPLACE INTO items VALUES (?,?)',[(i,'record-'+str(i)) for i in range(1,21)])
d.commit();d.close()
INNER
chown -R opsapp:opsapp /var/lib/ops-lab
rm -f /etc/nginx/sites-enabled/default
cat > /etc/nginx/conf.d/ops-lab.conf <<'NGINX'
server { listen 18880; server_name _; location / { proxy_pass http://127.0.0.1:18881; } }
NGINX
mkfs.ext4 -F /dev/vdb
install -d -m 755 /srv/ops-data
mount /dev/vdb /srv/ops-data
printf '/dev/vdb /srv/ops-data ext4 defaults 0 0\\n' >> /etc/fstab
install -d -m 700 /var/lib/ops-harness
printf 'Protected fixture evidence\\n' > /var/lib/ops-harness/protected-canary
systemctl daemon-reload
systemctl enable --now ops-demo nginx
systemctl disable --now unattended-upgrades || true
printf 'Provisioned\\n' > /var/lib/ops-harness/provision-complete
'''
cloud={'hostname':'ops-lab','manage_etc_hosts':True,'ssh_pwauth':False,
 'ssh_keys':{'ed25519_private':(private/'guest_host_key').read_text(),'ed25519_public':(private/'guest_host_key.pub').read_text().strip()},
 'users':[{'name':'harness','sudo':'ALL=(ALL) NOPASSWD:ALL','shell':'/bin/bash','ssh_authorized_keys':[(private/'harness_key.pub').read_text().strip()]}],
 'package_update':True,'packages':['python3','openssh-server','sudo','nginx','sqlite3','dnsutils','iproute2','iptables','acl','openssl','curl','lsof','stress-ng','rsync'],
 'write_files':[{'path':'/opt/ops-lab/service.py','permissions':'0644','content':health},{'path':'/etc/systemd/system/ops-demo.service','permissions':'0644','content':unit},{'path':'/opt/ops-lab/provision.sh','permissions':'0700','content':provision}],
 'runcmd':[['bash','/opt/ops-lab/provision.sh']]}
(root/'user-data').write_text('#cloud-config\n'+yaml.safe_dump(cloud,sort_keys=False))
(root/'meta-data').write_text('instance-id: ops-lab-build-20260930\nlocal-hostname: ops-lab\n')
mount=str(root)+':/lab'
for args in [ ['qemu-img','create','-f','qcow2','-F','qcow2','-b','/lab/'+base,'/lab/work.qcow2'],['qemu-img','resize','/lab/work.qcow2','10G'],['qemu-img','create','-f','qcow2','/lab/data.qcow2','128M'],['genisoimage','-output','/lab/seed.iso','-volid','cidata','-joliet','-rock','/lab/user-data','/lab/meta-data']]:
 subprocess.run(['docker','run','--rm','-v',mount,'--entrypoint',args[0],image,*args[1:]],check=True)
cmd=['docker','run','-d','--name','anthos-ops-lab','--device','/dev/kvm','--memory','2g','--cpus','2','-p','127.0.0.1:22219:2222','-p','127.0.0.1:28880:18880','-v',mount,image,'-enable-kvm','-cpu','host','-smp','2','-m','1536','-display','none','-serial','file:/lab/serial.log','-drive','file=/lab/work.qcow2,if=virtio,format=qcow2','-drive','file=/lab/data.qcow2,if=virtio,format=qcow2,id=opsdata','-drive','file=/lab/seed.iso,media=cdrom,readonly=on','-netdev','user,id=net0,hostfwd=tcp:0.0.0.0:2222-:22,hostfwd=tcp:0.0.0.0:18880-:18880','-device','virtio-net-pci,netdev=net0','-qmp','unix:/lab/qmp.sock,server=on,wait=off']
(root/'build-command.json').write_text(json.dumps(cmd,indent=2))
subprocess.run(cmd,check=True)
print('Disposable VM provisioning launched; models are not connected to it.',flush=True)
