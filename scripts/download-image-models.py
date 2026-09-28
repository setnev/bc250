import pathlib,json,subprocess,concurrent.futures,time
import argparse
parser=argparse.ArgumentParser(description='Fetch pinned image-benchmark weights and verify checksums.')
parser.add_argument('--root',type=pathlib.Path,required=True)
parser.add_argument('--manifest',type=pathlib.Path,required=True)
args=parser.parse_args()
p=args.root.resolve();p.mkdir(parents=True,exist_ok=True)
d=p/'models';d.mkdir(exist_ok=True)
def get(m):
 f=d/m['local_name'];partial=f.with_suffix(f.suffix+'.part')
 if not f.exists():
  subprocess.run(['curl','-fL','--retry','5','--retry-all-errors','--connect-timeout','20','-C','-','--output',str(partial),m['url']],check=True,stdout=subprocess.DEVNULL,stderr=(p/(m['local_name']+'.download.log')).open('w'))
  assert partial.stat().st_size==m['bytes']
  result=subprocess.check_output(['sha256sum',str(partial)],text=True).split()[0]
  assert result==m['sha256'],m['local_name']
  partial.rename(f)
 assert f.stat().st_size==m['bytes']
 assert subprocess.check_output(['sha256sum',str(f)],text=True).split()[0]==m['sha256']
 print(json.dumps({'verified':m['local_name'],'bytes':f.stat().st_size}),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(get,json.loads(args.manifest.read_text())))
(p/'download-complete.txt').write_text(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
