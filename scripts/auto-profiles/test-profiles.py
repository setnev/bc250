"""Restricted clock/voltage trials; serial requests and fail-closed thermal guard."""
import pathlib,json,subprocess,time,threading,signal,os,urllib.request,hashlib
ROOT=pathlib.Path(__file__).resolve().parent;OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
# Reuse the already-tested request and telemetry functions without its entry point.
import bench_support
ns=vars(bench_support)
def control(*args):return json.loads(subprocess.check_output(['python3',str(ROOT/'clock.py'),*map(str,args)],text=True,timeout=5))
profiles=[(1700,100),(1700,102),(1700,104),(1800,100)]
cases=ns['CASES'];allrows=[];previously_active=[];stop=threading.Event();fault=[];active=[None];label=['idle'];samples=[]
def monitor():
 with (OUT/'telemetry.jsonl').open('w') as f:
  while not stop.is_set():
   p=active[0]
   if p and p.poll() is None:
    try:
     m=ns['telemetry'](p.pid);m.update(label=label[0],monotonic=time.monotonic());samples.append(m);f.write(json.dumps(m)+'\n');f.flush()
     if m['gpu_edge_c']>=85 or m['host_available_bytes']<384*2**20:
      fault.append(label[0]);os.killpg(p.pid,signal.SIGTERM);break
    except FileNotFoundError:pass
   stop.wait(.5)
threading.Thread(target=monitor,daemon=True).start()
try:
 previously_active=[unit for unit in bench_support.MANAGED_UNITS if subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0]
 subprocess.run(['systemctl','stop',*bench_support.MANAGED_UNITS],check=True)
 for name,model,proj in ns['MODELS']:
  control('set',1700,100)
  cmd=[ns['BIN'],'-m',model,'--mmproj',str(ns['ROOT']/'models'/proj),'--host','127.0.0.1','--port','18086','-c','8192','-b','128','-ub','128','-t','6','-ngl','99','-fa','on','--parallel','1','--jinja','--reasoning','off','--cache-ram','0','--perf']
  baseline={}
  with (OUT/(name+'-server.log')).open('w') as log:
   p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);active[0]=p
   try:
    start=time.monotonic()
    while True:
     if p.poll() is not None or time.monotonic()-start>180:raise RuntimeError('model failed loading')
     try:
      with urllib.request.urlopen(ns['URL']+'/health',timeout=2) as r:
       if r.status==200:break
     except OSError:time.sleep(1)
    for mhz,vid in profiles:
     label[0]=f'{name}-{mhz}-{vid}';actual=control('set',mhz,vid)
     assert actual['gfx_frequency_mhz']==mhz and actual['gfx_vid']==vid
     jobs=[('warmup',[{'role':'user','content':'Reply only OK.'}])]
     for repeat in range(3):
      jobs += [(f'vision-{repeat}',[ns['image_message'](cases[0])]),(f'text-{repeat}',[{'role':'user','content':'Explain how a database transaction provides atomicity, consistency, isolation and durability. Give concrete examples and continue for at least 400 words.'}])]
     for job,messages in jobs:
      label[0]=f'{name}-{mhz}-{vid}-{job}';offset=len(samples);r=ns['request'](messages)
      digest=hashlib.sha256(r['answer'].encode()).hexdigest()
      if mhz==1700 and vid==100:baseline[job]=digest
      r.update(model=name,job=job,profile=actual,output_sha256=digest,matches_baseline=digest==baseline.get(job),peak_edge_c=max((x['gpu_edge_c'] for x in samples[offset:]),default=None),clock_after=control())
      allrows.append(r);(OUT/'trials.json').write_text(json.dumps(allrows,indent=2)+'\n')
      print(name,mhz,vid,job,round(r['wall_seconds'],2),round(r['timings']['predicted_per_second'],2),r['matches_baseline'],r['peak_edge_c'],flush=True)
      if fault or r['clock_after']['gfx_frequency_mhz']!=mhz:raise RuntimeError('thermal guard or clock mismatch')
      if not r['matches_baseline']:raise RuntimeError('output changed from baseline; trial stopped for review')
   finally:
    if p.poll() is None:
     os.killpg(p.pid,signal.SIGTERM)
     try:p.wait(10)
     except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    active[0]=None
 (OUT/'complete.txt').write_text('all profiles completed\n')
finally:
 stop.set();control('restore');subprocess.run(['systemctl','start',*previously_active]) if previously_active else None
