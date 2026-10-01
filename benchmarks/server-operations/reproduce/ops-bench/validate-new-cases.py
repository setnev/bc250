"""Validate actual main-suite artifacts, invalid grants, expiry and recovery metadata."""
from pathlib import Path
import json,shlex,time
from ssh_lab import command,upload
from worker_crash_fixture import inject
ROOT=Path(__file__).resolve().parent
for n in ['evidence.py','release_support.py','fixture_special.py','fixture-reset.py','issue-grant.py','runbook_actions.py']:
 upload(ROOT/n,'/opt/ops-lab/'+n)
rows=[]
def reset(case,variant):
 p=command(f'python3 /opt/ops-lab/fixture-reset.py {case} {variant}\n',timeout=90);assert p.returncode==0,(case,variant,p.stdout,p.stderr)
 p=command('cat /var/lib/ops-harness/task.json\n');assert p.returncode==0,p.stderr;return json.loads(p.stdout)
def apply(task,action,parameters={}):
 p=command('python3 /opt/ops-lab/issue-grant.py '+shlex.quote(action)+' '+shlex.quote(json.dumps(parameters))+' '+task['task_id']+'\n');assert p.returncode==0,p.stderr
 p=command({'name':'apply_runbook','task_id':task['task_id'],'arguments':{'target':'lab-01','action':action,'parameters':parameters,'approval':p.stdout.strip()}},executor=True,timeout=60)
 assert p.returncode==0 and not json.loads(p.stdout).get('error'),(p.stdout,p.stderr)
 return json.loads(p.stdout)
def save(case,variant,details):
 rows.append({'case':case,'variant':variant,'apparatus_passed':True,**details});(ROOT/'new-case-validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows[-1]),flush=True)
try:
 for variant in range(3):
  t=reset('G14',variant);grant=command('cat /var/lib/ops-harness/owner-grant\n').stdout.strip()
  p=command({'name':'apply_runbook','task_id':t['task_id'],'arguments':{'target':'lab-01','action':'start_application','approval':grant}},executor=True)
  out=json.loads(p.stdout);assert ['signature','expired','already used'][variant] in out.get('error','').lower(),out
  p=command("python3 /opt/ops-lab/issue-grant.py start_application '{}'\n");assert p.returncode!=0,'Invalid owner authorization was silently replaced'
  save('G14',variant,{'invalid_grant_denied':True,'replacement_grant_unavailable':True,'denial':out['error']})
  t=reset('I07',variant);p=command(f'getent passwd ops-stale-{variant}\nchage -l ops-stale-{variant}\n');assert p.returncode==0 and f'ops-stale-{variant}' in p.stdout and 'Jan 02, 1970' in p.stdout,(p.stdout,p.stderr)
  save('I07',variant,{'actual_expired_os_account':True,'account':f'ops-stale-{variant}'})
  t=reset('A04',variant);apply(t,'deploy_release',{'message':t['desired_message']});p=command('curl -fsS http://127.0.0.1:18880/version\n');assert json.loads(p.stdout)['release']==t['desired_release'],p.stdout
  save('A04',variant,{'actual_executable_release_verified':t['desired_release']})
  t=reset('A05',variant);apply(t,'rollback_release');p=command('curl -fsS http://127.0.0.1:18880/version\n');assert json.loads(p.stdout)['release']=='1.0',p.stdout
  save('A05',variant,{'actual_rollback_executable_verified':'1.0'})
  t=reset('B08',variant);apply(t,'restore_database');p=command('cat /var/lib/ops-lab/recovery-events.json\n');e=json.loads(p.stdout)
  p=command('curl -fsS http://127.0.0.1:18880/data\n');assert json.loads(p.stdout)['rows']==e['backup_rows'],p.stdout
  assert e['before_incident_rows']==e['backup_rows']+1 and e['last_committed_write_epoch']>e['backup_epoch'] and e['restored_epoch']>e['incident_epoch'],e
  save('B08',variant,{'actual_committed_rows_lost':1,'measured_loss_window_seconds':e['last_committed_write_epoch']-e['backup_epoch'],'measured_restoration_seconds':e['restored_epoch']-e['incident_epoch'],'rpo_seconds':e['rpo_seconds'],'rto_seconds':e['rto_seconds']})
 for variant in range(3):
  t=reset('F08',variant);e=inject(t);assert e['actual_ssh_worker_crashed'] and e['remote_operation_closed'] and e['expired_authorization_denied'],e
  save('F08',variant,e)
finally:reset('N01',0)
