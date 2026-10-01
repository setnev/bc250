"""Trusted harness-only grant issuer; never exposed as a model tool."""
from pathlib import Path
import json,sys
from policy import Policy,Scope
from task_registry import load
p=Path('/var/lib/ops-harness');task=load(sys.argv[3] if len(sys.argv)>3 else None)
if task.get('grant_policy')=='invalid_owner_token':raise ValueError('Owner token invalid; replacement authorization is unavailable')
action=sys.argv[1];parameters=json.loads(sys.argv[2])
scope=Scope('lab-01',task['task_id'],frozenset(),frozenset(task['allowed_runbooks']),task['expires_epoch'])
policy=Policy(scope,bytes.fromhex((p/'grant-key').read_text().strip()))
print(policy.issue(action,json.dumps(parameters,sort_keys=True,separators=(',',':')),ttl=30))
