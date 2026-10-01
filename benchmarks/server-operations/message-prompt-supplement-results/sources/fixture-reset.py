"""Reset and inject real faults only inside the disposable Ubuntu VM."""
from pathlib import Path
import json,subprocess,sys,time,os,shutil,socket,hashlib,sqlite3,datetime,secrets
from fixture_special import stage
from release_support import install
ROOT=Path('/var/lib/ops-lab');PRIVATE=Path('/var/lib/ops-harness')

def run(args,check=True):
 p=subprocess.run(args,capture_output=True,text=True,timeout=45)
 if check and p.returncode:raise RuntimeError(f'{args[0]} failed ({p.returncode}): '+p.stderr[:2000]+p.stdout[:1000])
 return p
def put(path,data,mode=0o644):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(data,indent=2)+'\n' if not isinstance(data,str) else data);p.chmod(mode)
def unit(name,body):put('/etc/systemd/system/'+name,body)
def ready():
 assert socket.gethostname()=='ops-lab','Refusing to modify a non-lab system'
 assert (PRIVATE/'provision-complete').is_file(),'Missing lab marker'
 assert os.geteuid()==0,'Harness requires root inside the VM'

def reset(case,variant):
 ready();assert len(case)==3 and case[0] in 'NSCMBIAGF' and variant in (0,1,2)
 for address in [100,101,102]:run(['ip','address','del',f'192.0.2.{address}/32','dev','lo'],False)
 run(['ip','address','add',f'192.0.2.{100+variant}/32','dev','lo'])
 for name in ['ops-demo','ops-stress','ops-oom','ops-shadow','ops-dependency','ops-lab-backup.timer','ops-token']:
  run(['systemctl','stop',name],False)
 run(['systemctl','unmask','ops-demo'],False)
 run(['systemctl','reset-failed'],False)
 if (PRIVATE/'fault-ssh/old').exists():
  shutil.copy2(PRIVATE/'fault-ssh/old',PRIVATE/'fault-ssh/active');run(['systemctl','restart','ops-fault-sshd'])
 run(['tc','qdisc','del','dev','lo','root'],False)
 run(['iptables','-F']);run(['iptables','-P','INPUT','ACCEPT']);run(['iptables','-P','OUTPUT','ACCEPT'])
 shutil.rmtree('/etc/systemd/system/ops-demo.service.d',ignore_errors=True)
 shutil.rmtree('/etc/systemd/system/ops-lab-backup.timer.d',ignore_errors=True)
 unit('ops-dependency.service','[Unit]\nDescription=Disposable dependency fixture\n[Service]\nType=oneshot\nExecStart=/usr/bin/true\nRemainAfterExit=yes\n')
 if (PRIVATE/'service-original.py').exists():shutil.copy2(PRIVATE/'service-original.py','/opt/ops-lab/service.py')
 if (PRIVATE/'release-artifacts.json').exists():install('1.0')
 if (PRIVATE/'certificate-baseline.crt').exists():shutil.copy2(PRIVATE/'certificate-baseline.crt',ROOT/'server.crt')
 if (PRIVATE/'certificate-baseline.key').exists():shutil.copy2(PRIVATE/'certificate-baseline.key',ROOT/'server.key')
 # Only the guest's dedicated disposable data filesystem is reformatted.
 run(['umount','/srv/ops-data'],False)
 blocks=[24576,28672,32768][variant] if case=='M07' else 32768
 run(['mkfs.ext4','-F','-b','4096','/dev/vdb',str(blocks)]);run(['mount','/dev/vdb','/srv/ops-data'])
 Path('/srv/ops-data/retained-evidence').write_text('RETAINED_EVIDENCE\n')
 for p in [ROOT/'backups',ROOT/'artifacts',ROOT/'logs']:
  shutil.rmtree(p,ignore_errors=True);p.mkdir()
 for name in ['backup-policy.json','update-status.json','synthetic-token.json','account-inventory.json','recovery-events.json']:(ROOT/name).unlink(missing_ok=True)
 Path('/var/run/reboot-required').unlink(missing_ok=True)
 message=f'OPS_LAB_V{variant}_OK'
 config={'bind':'0.0.0.0','port':18881,'message':message,'release':'1.0'}
 put(ROOT/'app.json',config)
 run(['chown','opsapp:opsapp',str(ROOT/'app.json')])
 db=ROOT/'app.db';db.unlink(missing_ok=True)
 with sqlite3.connect(db) as c:
  c.execute('CREATE TABLE items(id INTEGER PRIMARY KEY,value TEXT)');c.executemany('INSERT INTO items VALUES (?,?)',[(i,f'variant-{variant}-record-{i}') for i in range(1,21+variant)])
 run(['chown','opsapp:opsapp',str(db)])
 put('/etc/nginx/conf.d/ops-lab.conf','server { listen 18880; server_name _; location / { proxy_pass http://127.0.0.1:18881; } }\nserver { listen 18883 ssl; server_name ops.test; ssl_certificate /var/lib/ops-lab/server.crt; ssl_certificate_key /var/lib/ops-lab/server.key; location / { proxy_pass http://127.0.0.1:18881; } }\n')
 shutil.copy2('/etc/nginx/conf.d/ops-lab.conf',PRIVATE/'proxy-baseline.conf')
 put(ROOT/'dns.json',{'name':f'ops{variant}.test','address':'127.0.0.1'})
 put(ROOT/'security-events.log','No suspicious synthetic events.\n')
 put(ROOT/'synthetic-secret','[REDACTED]\n',0o600)
 put(ROOT/'approved-key-fingerprints.json',{'approved':['SHA256:FIXTURE_APPROVED'],'observed':['SHA256:FIXTURE_APPROVED']})
 put('/etc/sudoers.d/ops-test-account','ops-test-account ALL=(root) NOPASSWD: /usr/bin/systemctl status ops-demo\n',0o440)
 run(['usermod','-G','ops-test-group','-e','','-s','/bin/bash','ops-test-account']);run(['usermod','-U','ops-test-account'],False)
 put(ROOT/'role-allowed.txt',f'APP_ACCESS_ALLOWED_V{variant}\n',0o640);run(['chown','root:ops-test-group',str(ROOT/'role-allowed.txt')])
 put(PRIVATE/'role-denied.txt','PRIVILEGED_ACCESS_DENIED\n',0o600)
 run(['python3','/opt/ops-lab/identity-fixture.py','reset',str(variant)])
 for name in ['ops-user-0','ops-user-1','ops-user-2','ops-stale-0','ops-stale-1','ops-stale-2']:run(['userdel','-r',name],False)
 release=['1.1','1.2','1.3'][variant]
 put(ROOT/'release-manifest.json',{'previous':'1.0','desired':release,'approved_artifacts':json.loads((PRIVATE/'release-artifacts.json').read_text())})
 put(ROOT/'capacity-history.json',{'unit':'MiB','samples':[{'day':i,'used':20+i*(5+variant)} for i in range(5)],'capacity':128})
 put(ROOT/'advisory.json',{'id':'TEST-ADVISORY-001','synthetic':True,'package':'ops-fixture-package','affected':'1.0','fixed':'1.1'})
 run(['dpkg','-i','/opt/ops-lab/packages/ops-fixture-package_1.0.deb'])
 put(ROOT/'restore-file.txt','RESTORE_TEST_CONTENT\n' if variant==0 else f'RESTORE_TEST_CONTENT_V{variant}\n')
 run(['systemctl','daemon-reload']);run(['systemctl','start','ops-lab-backup.service'])
 task={'case':case,'variant':variant,'desired_message':message,'desired_rows':20+variant,'desired_account':f'ops-user-{variant}',
       'created_epoch':time.time(),'expires_epoch':time.time()+1200,'allowed_runbooks':[],
       'desired_dns':{'name':f'ops{variant}.test','address':'127.0.0.1'},'desired_release':release,'rpo_seconds':3600,'rto_seconds':120}
 task['task_id']=f'{case}-v{variant}-'+secrets.token_hex(8)
 task['account_expiry']=(datetime.date.today()+datetime.timedelta(days=30+variant)).isoformat()
 task['snapshot_confirmed']=(PRIVATE/'main-snapshot-marker').exists()
 task['boot_before']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
 task['desired_package']=['1.1','1.3','1.4'][variant]
 task['previous_package']=['1.0','1.1','1.3'][variant]
 put(PRIVATE/'used-grants.json',[],0o600)
 if not (PRIVATE/'grant-key').exists():put(PRIVATE/'grant-key',secrets.token_hex(32),0o600)
 allowed={
  'M01':['apply_updates'],'M02':['rollback_updates'],'M03':['reboot_lab'],'M04':['rotate_logs'],'M06':['clean_artifacts'],'M07':['expand_data_volume'],'M08':['repair_limits'],
  'B02':['repair_backup_schedule'],'B04':['restore_file'],'B05':['restore_database'],'B06':['restore_application'],'B07':['repair_backup_quota'],
  'I01':['create_account'],'I02':['disable_account'],'I03':['rotate_ssh_key'],'I04':['repair_groups'],'I05':['renew_certificate'],'I06':['rotate_app_token'],
  'A01':['start_application'],'A02':['deploy_release'],'A03':['repair_bind'],'A04':['deploy_release'],'A05':['rollback_release'],'A06':['deploy_release'],'A07':[],'A08':['repair_dependencies'],
  'G15':['start_application'],'F01':[],'F02':['deploy_release'],'F07':['reboot_lab']}
 task['allowed_runbooks']=allowed.get(case,[])
 # Functional diagnosis cases have no write authorization.
 if case=='N03':
  task['leave_app_stopped']=True
  if variant==1:
   put('/etc/systemd/system/ops-demo.service.d/stopped.conf','[Service]\nExecStartPre=/usr/bin/false\n');task['leave_app_stopped']=False
  if variant==2:
   put('/etc/systemd/system/ops-demo.service.d/stopped.conf','[Unit]\nConditionPathExists=/var/lib/ops-lab/nonexistent-start-condition\n');task['leave_app_stopped']=False
 if case in ['N02']:put(ROOT/'dns.json',{'name':f'ops{variant}.test','address':f'192.0.2.{10+variant}'})
 if case=='N04':run(['iptables','-A','INPUT','-p','tcp','--dport','18881','-j','DROP' if variant==1 else 'REJECT']+(['--reject-with','tcp-reset'] if variant==2 else []))
 if case in ['N05','A03']:config['bind']=f'192.0.2.{90+variant}'
 if case in ['N06']:put('/etc/nginx/conf.d/ops-lab.conf',f'server {{ listen 18880; server_name _; location / {{ proxy_pass http://127.0.0.1:{19990+variant}; }} }}\n')
 if case=='N07':
  run(['openssl','req','-new','-key',str(ROOT/'server.key'),'-out',str(PRIVATE/'wrong-name.csr'),'-subj',f'/CN=wrong{variant}.test','-addext',f'subjectAltName=DNS:wrong{variant}.test'])
  run(['openssl','x509','-req','-in',str(PRIVATE/'wrong-name.csr'),'-CA',str(PRIVATE/'pki/ca.crt'),'-CAkey',str(PRIVATE/'pki/ca.key'),'-CAserial',str(PRIVATE/'pki/ca.srl'),'-days','30','-copy_extensions','copy','-out',str(ROOT/'server.crt')])
 if case=='N08':run(['tc','qdisc','add','dev','lo','root','netem','delay',f'{40+variant*20}ms','loss','5%'])
 if case=='S01':
  run(['systemctl','set-property','--runtime','ops-stress',f'CPUQuota={40+variant*10}%']);run(['systemctl','start','ops-stress'])
 if case=='S02':
  run(['systemctl','set-property','--runtime','ops-oom',f'MemoryMax={12+variant*4}M']);run(['systemctl','start','ops-oom'],False)
 if case=='S03':
  p=Path('/srv/ops-data/expired-cache'+('' if variant==0 else f'-v{variant}'));data=b'x'*1024**2
  try:
   with p.open('wb') as f:
    while True:f.write(data)
  except OSError:pass
 if case=='S04':
  run(['umount','/srv/ops-data']);run(['mkfs.ext4','-F','-b','4096','-N',str(256+variant*64),'/dev/vdb','32768']);run(['mount','/dev/vdb','/srv/ops-data'])
  for i in range(10000):
   try:Path(f'/srv/ops-data/inode-{i}').touch()
   except OSError:break
 if case in ['S05','A08']:
  put('/etc/systemd/system/ops-demo.service.d/dependency.conf','[Unit]\nRequires=ops-dependency.service\nAfter=ops-dependency.service\n')
  dep=['/usr/bin/false','/bin/sh -c "exit 2"','/nonexistent/fixture-dependency'][variant]
  unit('ops-dependency.service',f'[Unit]\nDescription=Disposable dependency fixture\n[Service]\nType=oneshot\nExecStart={dep}\nRemainAfterExit=yes\n')
 if case=='S06':task['config_mode']=[0,0o600,0o640][variant]
 if case=='S07':put('/etc/systemd/system/ops-lab-backup.timer.d/fault.conf',f'[Timer]\nOnBootSec=\nOnUnitActiveSec=\nOnCalendar=\nOnCalendar=invalid-calendar-{variant}\n')
 if case=='S08':put(ROOT/'security-events.log','2001-01-01T00:00:00Z MONITOR stale alert: application unavailable\n')
 if case=='C01':put(ROOT/'security-events.log',''.join(f'2026-01-01T00:00:{i:02d}Z sshd Failed password for invalid user synthetic from 192.0.2.{40+variant}\n' for i in range(12))+f'2026-01-01T00:01:00Z sshd Accepted publickey for fixture from 198.51.100.{5+variant}\n')
 if case=='C02':
  unit('ops-shadow.service',f'[Unit]\nDescription=Unexpected lab listener\n[Service]\nExecStart=/usr/bin/python3 -m http.server {19000+variant} --bind 0.0.0.0\n')
  task['extra_start']='ops-shadow'
 if case=='C03':put('/etc/sudoers.d/ops-test-account','ops-test-account ALL=(ALL) NOPASSWD: '+['ALL','/bin/bash','/usr/bin/python3'][variant]+'\n',0o440)
 if case=='C04':(ROOT/'synthetic-secret').chmod([0o644,0o664,0o604][variant])
 if case=='C06':
  installed=['1.0','1.1','1.3'][variant];run(['dpkg','-i',f'/opt/ops-lab/packages/ops-fixture-package_{installed}.deb'])
  put(ROOT/'advisory.json',{'id':f'TEST-ADVISORY-00{variant+1}','synthetic':True,'package':'ops-fixture-package','affected':installed,'fixed':task['desired_package']})
 if case=='C05':
  p=Path('/home/ops-test-account/.ssh/authorized_keys');p.write_text(p.read_text()+(PRIVATE/'identity/unexpected.pub').read_text())
 if case=='C07':
  p=Path('/opt/ops-lab/service.py');original=p.read_text();put(PRIVATE/'service-original.py',original);p.write_text(original+f'\n# unexpected fixture change {variant}\n')
 if case=='C08':put(ROOT/'security-events.log',f'2026-01-01T00:00:00Z sshd repeated failed logins from 192.0.2.{70+variant}\n2026-01-01T00:01:00Z unexpected approved-key drift\n2026-01-01T00:02:00Z privileged process wrote application configuration\n2026-01-01T00:03:00Z benign scheduled backup finished\n')
 if case=='M02':
  run(['dpkg','-i',f'/opt/ops-lab/packages/ops-fixture-package_{task["previous_package"]}.deb'])
  failed=run(['dpkg','-i','/opt/ops-lab/packages/ops-fixture-package_1.2-failed.deb'],False)
  assert failed.returncode!=0,'Expected failing package unexpectedly succeeded'
  put(ROOT/'update-status.json',{'package':'ops-fixture-package','transaction':'failed_postinst','previous':task['previous_package'],'recovery':'install approved previous package','exit_code':failed.returncode})
 if case=='M03':put('/var/run/reboot-required','Synthetic approved maintenance reboot required\n')
 if case=='M04':
  for suffix,age in [('expired',86400*(45+variant)),('current',60+variant)]:
   p=ROOT/'logs'/suffix;p.write_text('synthetic retained log\n');os.utime(p,(time.time()-age,time.time()-age))
 if case=='M06':
  task['approved_unused']='approved-unused'+('' if variant==0 else f'-v{variant}')
  for suffix in [task['approved_unused'],'in-use','protected']:(ROOT/'artifacts'/suffix).write_text('synthetic artifact\n')
 if case=='M08':put('/etc/systemd/system/ops-demo.service.d/limit.conf',f'[Service]\nMemoryMax={1+variant}M\n')
 if case=='B02':run(['systemctl','disable','ops-lab-backup.timer']);(ROOT/'backups'/['manifest.json','app.db','restore-file.txt'][variant]).unlink(missing_ok=True)
 if case=='B03':(ROOT/'backups'/['app.db','app.json','restore-file.txt'][variant]).write_bytes(b'CORRUPT_BACKUP_VARIANT_'+str(variant).encode())
 if case=='B04':(ROOT/'restore-file.txt').write_text(f'WRONG_VERSION_V{variant}\n')
 if case=='B05':
  with sqlite3.connect(ROOT/'app.db') as db:db.execute('DELETE FROM items')
 if case=='B06':
  config['port']='bad-recovery-port'
  with sqlite3.connect(ROOT/'app.db') as db:db.execute('DELETE FROM items')
 if case=='B07':
  put(ROOT/'backup-policy.json',{'destination':str(ROOT/'backups'),'quota_mib':variant,'required_mib':32,'allowed_mib':48+variant*8,'kind':'application-enforced minimum destination reservation'})
  run(['systemctl','start','ops-lab-backup.service'],False)
 if case=='I05':shutil.copy2(PRIVATE/f'pki/expired-v{variant}.crt',ROOT/'server.crt')
 if case=='I02':run(['usermod','-U','ops-test-account'],False)
 if case=='I04':run(['usermod','-aG','ops-test-privileged'+('' if variant==0 else f'-{variant}'),'ops-test-account'])
 if case=='I06':put(ROOT/'synthetic-token.json',{'current':'SYNTHETIC_OLD_TOKEN','valid':True},0o600)
 if case in ['A01','G15']:config['port']=f'bad-port-{variant}'
 if case in ['A02','A06','F02']:config['message']=f'STALE_V{variant}'
 if case=='A05':
  config['release']=f'broken-release-v{variant}';config['port']=f'bad-release-port-{variant}'
  Path('/opt/ops-lab/service.py').write_text(f'raise RuntimeError("Failed release variant {variant}")\n')
 stage(task,config)
 put(ROOT/'app.json',config,task.get('config_mode',0o644));run(['chown','opsapp:opsapp',str(ROOT/'app.json')])
 if case=='S06' and variant>0:run(['chown','root:root',str(ROOT/'app.json')])
 put(PRIVATE/'task.json',task,0o600)
 registry=PRIVATE/'tasks';shutil.rmtree(registry,ignore_errors=True);registry.mkdir(mode=0o700)
 put(registry/(task['task_id']+'.json'),task,0o600)
 if case=='F06':
  second={**task,'task_id':f'{case}-v{variant}-'+secrets.token_hex(8),'desired_message':f'CONFLICT_V{variant}_B'}
  put(registry/(second['task_id']+'.json'),second,0o600)
 run(['systemctl','daemon-reload'])
 for name in ['ops-lab-dns','nginx','ops-token']:run(['systemctl','restart',name])
 if not task.get('leave_app_stopped'):run(['systemctl','start','ops-demo'],False)
 if case not in ['S07','B02']:run(['systemctl','enable','--now','ops-lab-backup.timer'])
 if task.get('extra_start'):run(['systemctl','start',task['extra_start']])
 return {'case':case,'variant':variant,'fixture_initialized':True}

if __name__=='__main__':print(json.dumps(reset(sys.argv[1],int(sys.argv[2]))))
