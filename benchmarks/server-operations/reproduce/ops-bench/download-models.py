"""Fetch the exact pinned benchmark GGUFs; run this on the inference host."""
from pathlib import Path
import argparse, hashlib, json, os, urllib.request

ROOT=Path('/opt/bc250-mod-prep')
DIRECTORIES={'qwen3.5-0.8b':ROOT/'ops-bench/models','qwen3.5-2b':ROOT/'ops-bench/models','qwen3.5-4b':ROOT/'vision-bench/models','qwen3.5-9b':Path('/var/lib/bc250-ai/models')}

def verify(path, row):
    if path.stat().st_size!=row['size']:raise RuntimeError('Model byte count differs: '+row['model'])
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024**2),b''):h.update(block)
    if h.hexdigest()!=row['sha256']:raise RuntimeError('Model SHA-256 differs: '+row['model'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,default=Path(__file__).with_name('model-manifest-draft.json'));p.add_argument('--projections',action='store_true',help='Also download the existing production vision projectors for faithful text-only soak memory behavior');args=p.parse_args()
    rows=json.loads(args.manifest.read_text())
    if args.projections:
        for row in json.loads(Path(__file__).with_name('soak-projection-manifest.json').read_text()):
            row['_projection']=True;rows.append(row)
    for row in rows:
        directory=ROOT/'vision-bench/models' if row.get('_projection') else DIRECTORIES[row['model']];directory.mkdir(parents=True,exist_ok=True);dest=directory/row['filename']
        if dest.exists():verify(dest,row);print('Existing pinned model verified:',row['model'],flush=True);continue
        partial=dest.with_suffix(dest.suffix+'.part')
        # Never overwrite an unrelated interrupted file or an existing model.
        with partial.open('xb') as f:
            request=urllib.request.Request(row['url'],headers={'User-Agent':'Anthos.AI-operations-reproduction'})
            with urllib.request.urlopen(request,timeout=60) as response:
                for block in iter(lambda:response.read(8*1024**2),b''):f.write(block)
            f.flush();os.fsync(f.fileno())
        verify(partial,row);partial.rename(dest);print('Pinned model downloaded and verified:',row['model'],flush=True)

if __name__=='__main__':main()
