"""Concurrent SSH requests retain distinct immutable authorization contexts."""
from pathlib import Path
import json,shlex,concurrent.futures
from ssh_lab import command,upload
r=Path(__file__).resolve().parent
for n in ['fixture_special.py','fixture-reset.py','transport-faults.py','task_registry.py','evidence.py','runbook_actions.py','policy.py','issue-grant.py','vm_executor.py']:upload(r/n,'/opt/ops-lab/'+n)
def reset(case):
 p=command(f'python3 /opt/ops-lab/fixture-reset.py {case} 0\n',timeout=90);assert p.returncode==0,(p.stdout,p.stderr)
try:
 reset('F06')
 p=command("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nprint(json.dumps([json.loads(x.read_text()) for x in Path('/var/lib/ops-harness/tasks').glob('*.json')]))\nPY\n");contexts=json.loads(p.stdout);assert len(contexts)==2
 requests=[]
 for t in contexts:
  params={'message':t['desired_message']}
  p=command('python3 /opt/ops-lab/issue-grant.py deploy_release '+shlex.quote(json.dumps(params))+' '+shlex.quote(t['task_id'])+'\n');assert p.returncode==0,p.stderr
  requests.append({'name':'apply_runbook','task_id':t['task_id'],'arguments':{'target':'lab-01','action':'deploy_release','parameters':params,'approval':p.stdout.strip()}})
 wrong={**requests[0],'task_id':contexts[1]['task_id']}
 denied=json.loads(command(wrong,executor=True).stdout);assert 'scope mismatch' in denied.get('error','').lower(),denied
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(lambda q:command(q,executor=True),requests))
 for p in results:assert p.returncode==0 and not json.loads(p.stdout).get('error'),(p.stdout,p.stderr)
 p=command("python3 - <<'PY'\nimport json\nfrom pathlib import Path\np=Path('/var/lib/ops-harness');ids={x.stem for x in (p/'tasks').glob('*.json')};events=[json.loads(x) for x in (p/'mutations.jsonl').read_text().splitlines() if json.loads(x)['task'] in ids];print(json.dumps({'events':events,'message':json.loads(Path('/var/lib/ops-lab/app.json').read_text())['message']}))\nPY\n")
 state=json.loads(p.stdout);assert len(state['events'])==2 and len({x['task'] for x in state['events']})==2 and state['message'] in {t['desired_message'] for t in contexts},state
 record={'case':'F06','apparatus_passed':True,'distinct_contexts':2,'cross_context_grant_denied':True,'successful_serialized_mutations':2,'final_state_is_one_approved_request':True}
 (r/'context-validation.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
finally:reset('N01')
