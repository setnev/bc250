"""Image-profile screening with temperature guard and deterministic output comparison."""
import pathlib,json,subprocess,time,threading,signal,os,urllib.request,base64,hashlib
ROOT=pathlib.Path(__file__).resolve().parent;OUT=ROOT/'image-cooled-results';OUT.mkdir(exist_ok=True)
import bench_support
ns=vars(bench_support)
def control(*args):return json.loads(subprocess.check_output(['python3',str(ROOT/'clock.py'),*map(str,args)],text=True,timeout=5))
def http(path,payload=None):
 req=urllib.request.Request('http://127.0.0.1:18085'+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=600) as r:return json.load(r)
profiles=[(1700,100)];rows=[];previously_active=[];done=threading.Event();p=[None];label=['load'];samples=[];fault=[]
def monitor():
 with (OUT/'telemetry.jsonl').open('w') as f:
  while not done.is_set():
   proc=p[0]
   if proc and proc.poll() is None:
    try:
     m=ns['telemetry'](proc.pid);m.update(label=label[0],monotonic=time.monotonic());samples.append(m);f.write(json.dumps(m)+'\n');f.flush()
     if m['gpu_edge_c']>=85 or m['host_available_bytes']<384*2**20:
      fault.append(label[0]);os.killpg(proc.pid,signal.SIGTERM);break
    except FileNotFoundError:pass
   done.wait(.5)
threading.Thread(target=monitor,daemon=True).start()
try:
 subprocess.run(['systemctl','stop','bc250-api-gateway.service','bc250-ai.service','bc250-profile-controller.service'],check=True)
 for name in ['z-image','klein']:
  control('set',1700,100);cmd=[arg.replace('IMAGE_ROOT',os.environ['BC250_IMAGE_ROOT']) for arg in json.loads((ROOT/'image-commands.json').read_text())[name]];base={}
  with (OUT/(name+'-server.log')).open('w') as log:
   proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);p[0]=proc
   try:
    start=time.monotonic()
    while True:
     if proc.poll() is not None or time.monotonic()-start>240:raise RuntimeError('model failed loading')
     try:http('/v1/models');break
     except OSError:time.sleep(1)
    for mhz,vid in profiles:
     actual=control('set',mhz,vid)
     for run,size in enumerate([512,1024,1024,1024]):
      label[0]=f'{name}-{mhz}-{vid}-{size}-run{run}';offset=len(samples)
      prompt='A photorealistic small home server rack on a wooden workbench, three compact circuit boards beside it, neatly routed blue Ethernet cables, a warm desk lamp, realistic brushed metal, shallow depth of field. A white label clearly reads "Anthos.AI".'
      payload=dict(prompt=prompt,width=size,height=size,steps=8 if name=='z-image' else 4,cfg_scale=1.0,seed=42,batch_size=1,sampler_name='Euler',scheduler='discrete' if name=='z-image' else 'flux2')
      t=time.monotonic();response=http('/sdapi/v1/txt2img',payload);elapsed=time.monotonic()-t
      image=base64.b64decode(response['images'][0].split(',')[-1]);digest=hashlib.sha256(image).hexdigest();(OUT/(label[0]+'.png')).write_bytes(image)
      if size not in base:base[size]=digest
      r=dict(model=name,size=size,run=run,profile=actual,wall_seconds=elapsed,payload=payload,output_sha256=digest,matches_baseline=digest==base[size],peak_edge_c=max(x['gpu_edge_c'] for x in samples[offset:]),clock_after=control())
      rows.append(r);(OUT/'trials.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='payload'}),flush=True)
      if fault or not r['matches_baseline'] or r['clock_after']['gfx_frequency_mhz']!=mhz:raise RuntimeError('Guard, output mismatch, or clock mismatch')
   finally:
    if proc.poll() is None:
     os.killpg(proc.pid,signal.SIGTERM)
     try:proc.wait(10)
     except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    p[0]=None
 (OUT/'complete.txt').write_text('all image profiles completed\n')
finally:
 done.set();control('restore');subprocess.run(['systemctl','start','bc250-profile-controller.service','bc250-ai.service','bc250-api-gateway.service'])
