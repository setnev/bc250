"""One-shot real SSH connection termination; never touch the management daemon."""
from pathlib import Path
import os,signal,json,time
PRIVATE=Path('/var/lib/ops-harness')
def once(stage):
 task=json.loads((PRIVATE/'task.json').read_text());case=task['case']
 if (case,stage) not in [('F01','read'),('F02','committed')]:return
 marker=PRIVATE/('fault-'+stage)
 if marker.exists():return
 marker.write_text(task['task_id'])
 # Terminate only an ancestor serving this executor connection. Its parent
 # must not be PID 1, which excludes the long-lived SSH listener.
 pid=os.getppid()
 for _ in range(8):
  status=Path(f'/proc/{pid}/status').read_text();fields={x.split(':',1)[0]:x.split(':',1)[1].strip() for x in status.splitlines() if ':' in x}
  parent=int(fields['PPid'])
  if fields['Name']=='sshd' and parent>1:
   os.kill(pid,signal.SIGKILL);time.sleep(.1);return
  if parent<=1:break
  pid=parent
 raise RuntimeError('Executor SSH ancestor could not be isolated')
