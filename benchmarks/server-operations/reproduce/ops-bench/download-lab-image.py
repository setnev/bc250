"""Download and verify the pinned official Ubuntu cloud image for lab preparation."""
from pathlib import Path
import urllib.request,json,subprocess,hashlib
root=Path(__file__).resolve().parent/'lab-build'
base='https://cloud-images.ubuntu.com/noble/20260926/'
filename='noble-server-cloudimg-amd64.img'
with urllib.request.urlopen(base+'SHA256SUMS',timeout=40) as f:checks=f.read().decode()
lines=[s for s in checks.splitlines() if s.split()[-1].lstrip('*')==filename]
assert len(lines)==1
expected=lines[0].split()[0]
assert expected=='6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2', 'Cloud image no longer matches the as-tested pin'
p=root/filename
if not p.exists():
 part=p.with_suffix('.img.part')
 subprocess.run(['curl','-fL','--retry','4','-C','-','--silent','--show-error','-o',str(part),base+filename],check=True)
 part.rename(p)
h=hashlib.sha256()
with p.open('rb') as f:
 for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
assert h.hexdigest()==expected
(root/'image-manifest.json').write_text(json.dumps({'url':base+filename,'sha256':expected,'size':p.stat().st_size},indent=2)+'\n')
print('Official Ubuntu cloud image verified:',expected,flush=True)
