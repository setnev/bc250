"""Exercise the independent completion verifier against real reviewed operations."""
from pathlib import Path
import json,time,shlex
from ssh_lab import command,upload
from snapshot_control import restore
from harness_verify import initialized,completed
R=Path(__file__).resolve().parent
cases=['I01','I05','A02','A04','A05','A06','B02','B05','B06','B07','M07','G11']
rows=json.loads((R/'main-completion-validation.json').read_text()) if (R/'main-completion-validation.json').exists() else []
try:
 for case in cases:
  for v in range(3):
   if any(x['case']==case and x['variant']==v for x in rows):continue
   start=time.monotonic();restore();p=command(f'python3 /opt/ops-lab/fixture-reset.py {case} {v}\n',timeout=90);assert p.returncode==0,p.stderr
   task=json.loads(command('cat /var/lib/ops-harness/task.json\n').stdout)
   before=json.loads(command('python3 /opt/ops-lab/harness_verify.py\n').stdout);assert initialized(before,task)
   action=task['allowed_runbooks'][0];parameters={'message':task['desired_message']} if action=='deploy_release' else {}
   p=command('python3 /opt/ops-lab/issue-grant.py '+shlex.quote(action)+' '+shlex.quote(json.dumps(parameters))+' '+shlex.quote(task['task_id'])+'\n');assert p.returncode==0,p.stderr
   token=p.stdout.strip();p=command({'name':'apply_runbook','task_id':task['task_id'],'arguments':{'target':'lab-01','action':action,'parameters':parameters,'approval':token}},executor=True,timeout=90);assert p.returncode==0,p.stderr;result=json.loads(p.stdout);assert not result.get('error'),result
   after=json.loads(command('python3 /opt/ops-lab/harness_verify.py\n',timeout=45).stdout);checks=completed(before,after,task)
   row={'case':case,'variant':v,'real_operation':action,'result':result,'checks':checks,'before':before,'after':after,'seconds':time.monotonic()-start};rows.append(row);(R/'main-completion-validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps({k:x for k,x in row.items() if k not in ['before','after']}),flush=True)
   assert checks['state_outcome_passed'] and checks['protected_state_preserved'],(case,v,checks)
finally:restore()
