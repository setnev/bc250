import pathlib,json,subprocess,hashlib,concurrent.futures
R=pathlib.Path(__file__).parent;M=R/'models';M.mkdir(exist_ok=True)
def download(r):
 p=M/r['filename'];part=p.with_suffix(p.suffix+'.part')
 if not p.exists():
  subprocess.run(['curl','-fL','--retry','4','--retry-delay','3','-C','-','--silent','--show-error','-o',str(part),r['url']],check=True)
  part.rename(p)
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
 assert p.stat().st_size==r['size'] and h.hexdigest()==r['sha256'],r['filename']
 print(json.dumps({'verified':r['filename'],'size':r['size']}),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as e:list(e.map(download,json.loads((R/'weights.json').read_text())))
(R/'download-complete.txt').write_text('All model sizes and SHA256 values verified.\n')
