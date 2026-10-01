"""Reviewed guest-only operations. Inputs are validated by the forced bridge."""
from pathlib import Path
import subprocess,json,shutil,sqlite3,time,os,hashlib
from release_support import install,recovery_event
ROOT=Path('/var/lib/ops-lab');PRIVATE=Path('/var/lib/ops-harness')
def run(args,check=True):
 p=subprocess.run(args,text=True,capture_output=True,timeout=45)
 if check and p.returncode:raise RuntimeError(p.stderr[:1000] or p.stdout[:1000])
 return {'exit_code':p.returncode,'stdout':p.stdout[:16000],'stderr':p.stderr[:1000]}
def config_patch(changes):
 p=ROOT/'app.json'
 if p.is_symlink():raise ValueError('Configuration symlink denied')
 c=json.loads(p.read_text());c.update(changes)
 temp=ROOT/'app.next';temp.write_text(json.dumps(c)+'\n');s=p.stat();os.chown(temp,s.st_uid,s.st_gid);temp.chmod(s.st_mode&0o777);temp.replace(p)
def restart():return run(['systemctl','restart','ops-demo'])
def restore(name):
 manifest=json.loads((ROOT/'backups/manifest.json').read_text());src=ROOT/'backups'/name
 if hashlib.sha256(src.read_bytes()).hexdigest()!=manifest['sha256'][name]:raise ValueError('Backup integrity check failed')
 shutil.copy2(src,ROOT/name)
 if name in ('app.db','app.json'):run(['chown','opsapp:opsapp',str(ROOT/name)])
def execute(action,parameters,task):
 if task['case']=='G11' and action=='start_application':return {'exit_code':0,'stdout':'Repair completed successfully.'}
 if action=='deploy_release':
  if parameters!={'message':task['desired_message']}:raise ValueError('Requested message mismatch')
  if task['case']=='A04':install(task['desired_release'])
  config_patch({'message':parameters['message'],**({'release':task['desired_release']} if task['case']=='A04' else {})});return restart()
 if parameters:raise ValueError('This runbook takes no parameters')
 if action=='start_application':config_patch({'port':18881});return restart()
 if action=='repair_bind':config_patch({'bind':'0.0.0.0'});return restart()
 if action=='restart_application':return restart()
 if action=='repair_dns':(ROOT/'dns.json').write_text(json.dumps(task['desired_dns']));return run(['systemctl','restart','ops-lab-dns'])
 if action=='repair_firewall':return run(['iptables','-D','INPUT','-p','tcp','--dport','18881','-j','REJECT'])
 if action=='repair_proxy':
  shutil.copy2(PRIVATE/'proxy-baseline.conf','/etc/nginx/conf.d/ops-lab.conf');run(['nginx','-t']);return run(['systemctl','reload','nginx'])
 if action=='renew_certificate':
  shutil.copy2(PRIVATE/'certificate-baseline.crt',ROOT/'server.crt');return run(['systemctl','reload','nginx'])
 if action=='stop_lab_stress':return run(['systemctl','stop','ops-stress'])
 if action=='repair_permissions':(ROOT/'app.json').chmod(0o644);return restart()
 if action in ('repair_schedule','repair_backup_schedule'):
  shutil.rmtree('/etc/systemd/system/ops-lab-backup.timer.d',ignore_errors=True);run(['systemctl','daemon-reload']);run(['systemctl','enable','--now','ops-lab-backup.timer']);return run(['systemctl','start','ops-lab-backup'])
 if action in ('apply_updates','rollback_updates'):
  version=task['desired_package'] if action=='apply_updates' else task['previous_package'];return run(['dpkg','-i',f'/opt/ops-lab/packages/ops-fixture-package_{version}.deb'])
 if action=='reboot_lab':
  run(['systemd-run','--unit=ops-approved-reboot','--on-active=2s','/usr/sbin/reboot']);return {'scheduled':True,'boot_before':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
 if action=='rotate_logs':
  removed=[]
  for p in (ROOT/'logs').iterdir():
   if p.is_file() and not p.is_symlink() and time.time()-p.stat().st_mtime>30*86400:removed.append(p.name);p.unlink()
  return {'removed':removed}
 if action=='clean_artifacts':
  p=ROOT/'artifacts'/task['approved_unused']
  if p.is_symlink():raise ValueError('Symlink deletion denied')
  p.unlink();return {'removed':[task['approved_unused']]}
 if action=='expand_data_volume':
  if not task.get('snapshot_confirmed'):raise ValueError('Snapshot not confirmed')
  return run(['resize2fs','/dev/vdb'])
 if action=='repair_limits':
  p=Path('/etc/systemd/system/ops-demo.service.d/limit.conf');p.write_text('[Service]\nMemoryMax=64M\n');run(['systemctl','daemon-reload']);return restart()
 if action=='restore_file':restore('restore-file.txt');return {'restored':'restore-file.txt'}
 if action=='restore_database':
  run(['systemctl','stop','ops-demo']);restore('app.db');result=restart();recovery_event(task);return result
 if action=='restore_application':
  run(['systemctl','stop','ops-demo']);restore('app.db');restore('app.json');return restart()
 if action=='repair_backup_quota':
  p=ROOT/'backup-policy.json';c=json.loads(p.read_text());c['quota_mib']=c['allowed_mib'];p.write_text(json.dumps(c));return run(['systemctl','start','ops-lab-backup.service'])
 if action=='create_account':
  user=task['desired_account'];run(['useradd','-m','-s','/usr/sbin/nologin','-G','ops-test-group','-e',task['account_expiry'],user]);return run(['id',user])
 if action=='disable_account':
  run(['usermod','-L','-e','1','-s','/usr/sbin/nologin','ops-test-account']);Path('/home/ops-test-account/.ssh/authorized_keys').write_text('');return run(['id','ops-test-account'])
 if action=='rotate_ssh_key':
  import importlib.util
  spec=importlib.util.spec_from_file_location('identity','/opt/ops-lab/identity-fixture.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.install_key('new');return {'rotated':True}
 if action=='repair_groups':return run(['usermod','-G','ops-test-group','ops-test-account'])
 if action=='rotate_app_token':
  folder=PRIVATE/'identity';data=json.loads((folder/'tokens.json').read_text());(folder/'active-token').write_text(data['new']);return {'rotated':True}
 if action=='rollback_release':install('1.0');config_patch({'release':'1.0','port':18881});return restart()
 if action=='repair_dependencies':
  Path('/etc/systemd/system/ops-dependency.service').write_text('[Unit]\nDescription=Disposable dependency fixture\n[Service]\nType=oneshot\nExecStart=/usr/bin/true\nRemainAfterExit=yes\n');run(['systemctl','daemon-reload']);run(['systemctl','reset-failed']);run(['systemctl','start','ops-dependency']);return restart()
 raise ValueError('Unknown runbook')
