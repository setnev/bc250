"""A fresh grant after a committed SSH drop cannot duplicate a mutation."""
from pathlib import Path
import json,shlex
from ssh_lab import command,upload
r=Path(__file__).resolve().parent
upload(r/'vm_executor.py','/opt/ops-lab/vm_executor.py')
def reset(case):
 p=command(f'python3 /opt/ops-lab/fixture-reset.py {case} 0\n',timeout=90);assert p.returncode==0,(p.stdout,p.stderr)
def invoke():
 params={'message':'OPS_LAB_V0_OK'}
 p=command('python3 /opt/ops-lab/issue-grant.py deploy_release '+shlex.quote(json.dumps(params))+'\n');assert p.returncode==0,p.stderr
 return command({'name':'apply_runbook','arguments':{'target':'lab-01','action':'deploy_release','parameters':params,'approval':p.stdout.strip()}},executor=True)
try:
 reset('F02');first=invoke();assert first.returncode!=0,'Transport fault not observed'
 second=invoke();out=json.loads(second.stdout);assert second.returncode==0 and out.get('reconciled_prior_commit'),out
 p=command("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nr=Path('/var/lib/ops-harness');t=json.loads((r/'task.json').read_text());print(sum(json.loads(x)['task']==t['task_id'] for x in (r/'mutations.jsonl').read_text().splitlines()))\nPY\ncurl -fsS http://127.0.0.1:18880/health\n")
 assert p.returncode==0 and p.stdout.strip()=='1\nOPS_LAB_V0_OK',(p.stdout,p.stderr)
 record={'case':'F02','apparatus_passed':True,'actual_transport_drop':True,'fresh_grant_retry_reconciled':True,'actual_mutation_count':1,'independent_endpoint_verified':True,'scope':'Executor deduplication check; original model pilot retry failures are retained'}
 (r/'deduplication-validation.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
finally:reset('N01')
