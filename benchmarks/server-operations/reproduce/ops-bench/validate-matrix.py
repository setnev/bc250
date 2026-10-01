"""Check every approved fault variant before any main scored model run."""
from pathlib import Path
import json,shlex,argparse,time
from ssh_lab import command,upload
from harness_verify import initialized
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--from-case');parser.add_argument('--only-case');opts=parser.parse_args()
upload(ROOT/'harness_verify.py','/opt/ops-lab/harness_verify.py')
cases=json.loads((ROOT/'cases.json').read_text());rows=json.loads((ROOT/'matrix-validation.json').read_text()) if opts.from_case else []
started=opts.from_case is None
try:
 for case in cases:
  cid=case['id']
  if opts.only_case and cid!=opts.only_case:continue
  if cid==opts.from_case:started=True
  if not started:continue
  for variant in range(3):
   start=time.monotonic();p=command(f'python3 /opt/ops-lab/fixture-reset.py {cid} {variant}\n',timeout=90)
   assert p.returncode==0,(cid,variant,p.stdout,p.stderr)
   p=command('cat /var/lib/ops-harness/task.json\n');task=json.loads(p.stdout)
   p=command('python3 /opt/ops-lab/harness_verify.py\n',timeout=45);assert p.returncode==0,(cid,variant,p.stdout,p.stderr)
   state=json.loads(p.stdout);passed=initialized(state,task)
   rows=[x for x in rows if (x['case'],x['variant'])!=(cid,variant)]
   row={'case':cid,'variant':variant,'initial_fault_verified':passed,'seconds':time.monotonic()-start,'state':state};rows.append(row)
   (ROOT/'matrix-validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps({k:v for k,v in row.items() if k!='state'}),flush=True)
   assert passed,('Initial fault predicate failed',cid,variant,state)
finally:
 p=command('python3 /opt/ops-lab/fixture-reset.py N01 0\n',timeout=90);assert p.returncode==0,(p.stdout,p.stderr)
