"""Validate and install a real versioned application artifact in the lab guest."""
from pathlib import Path
import hashlib,json,shutil,time
ROOT=Path('/var/lib/ops-lab');PRIVATE=Path('/var/lib/ops-harness')
def install(version):
 manifest=json.loads((PRIVATE/'release-artifacts.json').read_text())
 if version not in manifest:raise ValueError('Release artifact not approved')
 src=Path('/opt/ops-lab/releases')/version/'service.py';target=Path('/opt/ops-lab/service.py')
 if target.is_symlink() or hashlib.sha256(src.read_bytes()).hexdigest()!=manifest[version]:raise ValueError('Release artifact integrity failed')
 shutil.copy2(src,target)
def recovery_event(task):
 if task['case']!='B08':return
 p=ROOT/'recovery-events.json';events=json.loads(p.read_text());events['restored_epoch']=time.time();p.write_text(json.dumps(events))
