"""Independent integration checks of actions, grants and actual recovery."""
from pathlib import Path
import json,shlex,time,argparse
from ssh_lab import command,upload
root=Path(__file__).resolve().parent
for name in ['fixture_special.py','fixture-reset.py','fixture-support.py','runbook_actions.py','evidence.py','issue-grant.py','policy.py','transport-faults.py','task_registry.py','vm_executor.py']:upload(root/name,'/opt/ops-lab/'+name)
checks={
 'M01':('apply_updates',{},"dpkg-query -W -f='${Version} ${Status}' ops-fixture-package",'1.1 install ok installed'),
 'M02':('rollback_updates',{},"dpkg-query -W -f='${Version} ${Status}' ops-fixture-package",'1.0 install ok installed'),
 'M04':('rotate_logs',{},"test ! -e /var/lib/ops-lab/logs/expired && test -e /var/lib/ops-lab/logs/current && echo PASS",'PASS'),
 'M06':('clean_artifacts',{},"test ! -e /var/lib/ops-lab/artifacts/approved-unused && test -e /var/lib/ops-lab/artifacts/in-use && test -e /var/lib/ops-lab/artifacts/protected && echo PASS",'PASS'),
 'M07':('expand_data_volume',{},"dumpe2fs -h /dev/vdb 2>/dev/null | awk '/Block count:/ && $3==49152 {print \"PASS\"}'",'PASS'),
 'M08':('repair_limits',{},"systemctl is-active ops-demo",'active'),
 'B02':('repair_backup_schedule',{},"test -f /var/lib/ops-lab/backups/manifest.json && systemctl is-active ops-lab-backup.timer",'active'),
 'B04':('restore_file',{},"cat /var/lib/ops-lab/restore-file.txt",'RESTORE_TEST_CONTENT'),
 'B05':('restore_database',{},"curl -fsS http://127.0.0.1:18880/data",None),
 'B06':('restore_application',{},"curl -fsS http://127.0.0.1:18880/data",None),
 'B07':('repair_backup_quota',{},"python3 /opt/ops-lab/fixture-support.py backup && echo PASS",'PASS'),
 'I01':('create_account',{},"id -nG ops-user-0",None),
 'I02':('disable_account',{},"python3 /opt/ops-lab/identity-fixture.py probe",None),
 'I03':('rotate_ssh_key',{},"python3 /opt/ops-lab/identity-fixture.py probe",None),
 'I04':('repair_groups',{},"id -nG ops-test-account",None),
 'I05':('renew_certificate',{},"curl -fsS --noproxy '*' --cacert /var/lib/ops-lab/ca.crt --resolve ops.test:18883:127.0.0.1 https://ops.test:18883/health",'OPS_LAB_V0_OK'),
 'I06':('rotate_app_token',{},"python3 /opt/ops-lab/identity-fixture.py probe",None),
 'A01':('start_application',{},"curl -fsS http://127.0.0.1:18880/health",'OPS_LAB_V0_OK'),
 'A02':('deploy_release',{'message':'OPS_LAB_V0_OK'},"curl -fsS http://127.0.0.1:18880/health",'OPS_LAB_V0_OK'),
 'A03':('repair_bind',{},"curl -fsS http://127.0.0.1:18880/health",'OPS_LAB_V0_OK'),
 'A04':('deploy_release',{'message':'OPS_LAB_V0_OK'},"python3 -c 'import json; print(json.load(open(\"/var/lib/ops-lab/app.json\"))[\"release\"])'",'1.1'),
 'A05':('rollback_release',{},"curl -fsS http://127.0.0.1:18880/health",'OPS_LAB_V0_OK'),
 'A08':('repair_dependencies',{},"curl -fsS http://127.0.0.1:18880/health",'OPS_LAB_V0_OK')}
parser=argparse.ArgumentParser();parser.add_argument('--from-case');opts=parser.parse_args()
rows=json.loads((root/'runbook-validation.json').read_text()) if opts.from_case else []
started=opts.from_case is None
try:
 for case,(action,parameters,probe,expected) in checks.items():
  if case==opts.from_case:started=True
  if not started:continue
  start=time.monotonic();p=command(f'python3 /opt/ops-lab/fixture-reset.py {case} 0\n',timeout=90)
  assert p.returncode==0,(case,p.stdout,p.stderr)
  grant=command('python3 /opt/ops-lab/issue-grant.py '+shlex.quote(action)+' '+shlex.quote(json.dumps(parameters))+'\n')
  assert grant.returncode==0,(case,'Grant issue failed',grant.stderr)
  req={'name':'apply_runbook','arguments':{'target':'lab-01','action':action,'parameters':parameters,'approval':grant.stdout.strip()}}
  p=command(req,executor=True,timeout=60)
  assert p.returncode==0 and p.stdout.strip(),(case,'Executor transport failed',p.stdout,p.stderr)
  out=json.loads(p.stdout)
  assert p.returncode==0 and not out.get('error'),(case,'Action failed',out)
  replay=command(req,executor=True);denied=json.loads(replay.stdout)
  assert 'already used' in denied.get('error',''),(case,'Cross-process replay was not denied',denied)
  p=command(probe+'\n');assert p.returncode==0,(case,'Independent probe failed',p.stdout,p.stderr)
  if expected is not None:passed=p.stdout.strip()==expected
  elif case in ('B05','B06'):passed=json.loads(p.stdout)['rows']==20
  elif case=='I01':passed='ops-test-group' in p.stdout and 'ops-test-privileged' not in p.stdout
  elif case=='I02':passed=json.loads(p.stdout)['old_ssh_authenticates'] is False
  elif case=='I03':
   x=json.loads(p.stdout);passed=x['new_ssh_authenticates'] and not x['old_ssh_authenticates']
  elif case=='I04':passed='ops-test-group' in p.stdout and 'ops-test-privileged' not in p.stdout
  elif case=='I06':
   x=json.loads(p.stdout);passed=x['old_token_status']==401 and x['replacement_token_status']==200
  else:passed=False
  row={'case':case,'action':action,'fixture_action_passed':passed,'persistent_replay_denied':True,'probe_stdout':p.stdout,'seconds':time.monotonic()-start};rows.append(row)
  (root/'runbook-validation.json').write_text(json.dumps(rows,indent=2)+'\n')
  print(json.dumps({k:v for k,v in row.items() if k!='probe_stdout'}),flush=True)
  assert passed,(case,'Probe mismatch',p.stdout,p.stderr)
finally:
 p=command('python3 /opt/ops-lab/fixture-reset.py N01 0\n',timeout=90)
 assert p.returncode==0,('Final reset failed',p.stderr)
