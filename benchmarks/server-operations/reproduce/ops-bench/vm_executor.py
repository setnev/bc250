"""SSH forced-command bridge with persistent grants and serialized mutations."""
from pathlib import Path
import json,sys,os,time,fcntl,socket,hashlib
from policy import arguments,PolicyError,READ_RESOURCES,RUNBOOKS,Policy,Scope
from evidence import read,verify
from runbook_actions import execute
from task_registry import load
import importlib.util
spec=importlib.util.spec_from_file_location('transport_faults','/opt/ops-lab/transport-faults.py');faults=importlib.util.module_from_spec(spec);spec.loader.exec_module(faults)
PRIVATE=Path('/var/lib/ops-harness')
def bridge(req):
 if socket.gethostname()!='ops-lab' or not (PRIVATE/'provision-complete').exists():raise PolicyError('Lab identity check failed')
 req=arguments(req,['name'],['arguments','task_id']);name=req['name'];args=req.get('arguments',{})
 task=load(req.get('task_id'))
 if name=='inspect':
  args=arguments(args,['target','resource'])
  if args['target']!='lab-01' or args['resource'] not in READ_RESOURCES:raise PolicyError('Inspection target or resource not approved')
  faults.once('read')
  return read(args['resource'])
 if name=='verify':
  args=arguments(args,['target','probe'])
  if args['target']!='lab-01':raise PolicyError('Target not approved')
  return verify(args['probe'])
 if name=='apply_runbook':
  args=arguments(args,['target','action'],['parameters','approval'])
  if args['target']!='lab-01' or args['action'] not in RUNBOOKS:raise PolicyError('Action not approved')
  parameters=args.get('parameters',{})
  if not isinstance(parameters,dict):raise PolicyError('Parameters must be an object')
  scope=Scope('lab-01',task['task_id'],frozenset(READ_RESOURCES),frozenset(task['allowed_runbooks']),task['expires_epoch'])
  policy=Policy(scope,bytes.fromhex((PRIVATE/'grant-key').read_text().strip()))
  used=PRIVATE/'used-grants.json';policy.used=set(json.loads(used.read_text()))
  policy.consume(args.get('approval',''),args['target'],args['action'],json.dumps(parameters,sort_keys=True,separators=(',',':')))
  temp=used.with_suffix('.next')
  with temp.open('w') as f:json.dump(sorted(policy.used),f);f.flush();os.fsync(f.fileno())
  temp.chmod(0o600);temp.replace(used)
  fd=os.open(PRIVATE,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
  # A fresh grant is not permission to repeat an already committed operation.
  identity=json.dumps([task['task_id'],args['action'],parameters],sort_keys=True,separators=(',',':'))
  folder=PRIVATE/'operations';folder.mkdir(mode=0o700,exist_ok=True)
  ledger=folder/(hashlib.sha256(identity.encode()).hexdigest()+'.json')
  if ledger.exists():
   previous=json.loads(ledger.read_text())
   if previous['state']=='committed':return {'reconciled_prior_commit':True,'previous_result':previous['result'],'requires_independent_verification':True}
   raise PolicyError('Prior operation outcome is uncertain; inspect state and escalate for fresh task authorization')
  def persist(record):
   temp=ledger.with_suffix('.next')
   with temp.open('w') as f:json.dump(record,f);f.flush();os.fsync(f.fileno())
   temp.chmod(0o600);temp.replace(ledger)
   fd=os.open(folder,os.O_RDONLY)
   try:os.fsync(fd)
   finally:os.close(fd)
  persist({'state':'pending','task':task['task_id'],'action':args['action']})
  result=execute(args['action'],parameters,task)
  persist({'state':'committed','task':task['task_id'],'action':args['action'],'result':result})
  with (PRIVATE/'mutations.jsonl').open('a') as f:
   f.write(json.dumps({'task':task['task_id'],'action':args['action'],'epoch':time.time()})+'\n');f.flush();os.fsync(f.fileno())
  faults.once('committed')
  return result
 raise PolicyError('Tool not approved')
def process(req):
 with (PRIVATE/'executor.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  try:result=bridge(req)
  except Exception as e:result={'error':str(e),'error_type':type(e).__name__}
  args=req.get('arguments',{}) if isinstance(req,dict) else {}
  with (PRIVATE/'audit.jsonl').open('a') as f:
   f.write(json.dumps({'epoch':time.time(),'tool':req.get('name') if isinstance(req,dict) else None,'target':args.get('target') if isinstance(args,dict) else None,'action':args.get('action') if isinstance(args,dict) else None,'denied':bool(result.get('error'))})+'\n')
  return result
if __name__=='__main__':
 try:
  line=sys.stdin.readline(65537)
  if len(line)>65536:raise PolicyError('Request too large')
  result=process(json.loads(line))
 except Exception as e:result={'error':str(e),'error_type':type(e).__name__}
 print(json.dumps(result))
