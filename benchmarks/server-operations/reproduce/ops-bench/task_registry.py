"""Immutable per-request contexts owned by the trusted lab harness."""
from pathlib import Path
import json,re
PRIVATE=Path('/var/lib/ops-harness')
def load(task_id=None):
 if task_id is None:return json.loads((PRIVATE/'task.json').read_text())
 if not isinstance(task_id,str) or not re.fullmatch(r'[NSCMBIAGF][0-9]{2}-v[0-2]-[0-9a-f]{16}',task_id):raise ValueError('Invalid task identity')
 return json.loads((PRIVATE/'tasks'/ (task_id+'.json')).read_text())
