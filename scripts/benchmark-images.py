import pathlib,subprocess,json,time,urllib.request,urllib.error,base64,threading,os,signal,sys,struct
import argparse
parser=argparse.ArgumentParser(description='Reproduce the BC250 Z-Image/Klein comparison. Run on the GPU host.')
parser.add_argument('--root',type=pathlib.Path,required=True,help='Directory containing build/bin/sd-server and models/')
parser.add_argument('--mode',choices=['smoke','full','stock','qualified'],default='qualified')
parser.add_argument('--clock-reader',type=pathlib.Path,required=True,help='Path to bc250-gpu-clock.py; queried without setting arguments')
parser.add_argument('--clock-mhz',type=int,default=1200,help='Expected SMU-reported clock during every request')
parser.add_argument('--chat-service',help='Optional systemd inference service to stop during testing and restart afterward')
args=parser.parse_args()
ROOT=args.root.resolve()
MODE=args.mode
OUT=ROOT/MODE;OUT.mkdir(exist_ok=True)
MODELS={
 'z-image':('z_image_turbo-Q5_0.gguf','Qwen3-4B-Instruct-2507-Q4_K_M.gguf','ae.safetensors',8,'discrete'),
 'klein':('flux-2-klein-4b-Q8_0.gguf','Qwen3-4B-Q4_K_M.gguf','flux2-vae.safetensors',4,'flux2')}
PROMPTS={
 'server':'A photorealistic small home server rack on a wooden workbench, three compact circuit boards beside it, neatly routed blue Ethernet cables, a warm desk lamp, realistic brushed metal, shallow depth of field. A white label clearly reads "ANTHOS AI".',
 'dungeon':'A cinematic fantasy dungeon, an ancient stone stairway descending to an ironbound wooden door, glowing cyan runes carved around the doorway, a single brass lantern casting warm light, mist near the floor, detailed weathered stone, wide composition, no people, no text.',
 'hands':'A studio photograph of two human hands holding a blue ceramic mug, anatomically correct fingers, natural skin texture, soft daylight, a plain neutral background, sharp focus on the hands and mug.'}
(OUT/'prompts.json').write_text(json.dumps(PROMPTS,indent=2)+'\n')
CG=pathlib.Path('/sys/fs/cgroup'+pathlib.Path('/proc/self/cgroup').read_text().strip().split('::',1)[1])
URL='http://127.0.0.1:18085'
def http(path,payload=None,timeout=600):
 req=urllib.request.Request(URL+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
def terminate(p):
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
def metrics(pid):
 mem={line.split(':')[0]:int(line.split()[1])*1024 for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if ':' in line and len(line.split())>=2}
 rss=0
 for line in pathlib.Path(f'/proc/{pid}/status').read_text().splitlines():
  if line.startswith('VmRSS:'):rss=int(line.split()[1])*1024
 d=pathlib.Path('/sys/class/drm/card1/device')
 data={'host_available_bytes':mem['MemAvailable'],'process_rss_bytes':rss,'cgroup_memory_bytes':int((CG/'memory.current').read_text()),'gpu_edge_c':max(int(p.read_text()) for p in (d/'hwmon').glob('hwmon*/temp1_input'))/1000}
 for kind in ('vram','gtt'):
  p=d/f'mem_info_{kind}_used'
  if p.exists():data[f'gpu_{kind}_used_bytes']=int(p.read_text())
 return data
def smu():
 return json.loads(subprocess.check_output(['/usr/bin/python3',str(args.clock_reader.resolve())],text=True,timeout=5))
def model_run(name):
 weights,te,vae,steps,scheduler=MODELS[name]
 cmd=[str(ROOT/'build/bin/sd-server'),'--diffusion-model',str(ROOT/'models'/weights),'--llm',str(ROOT/'models'/te),'--vae',str(ROOT/'models'/vae),'--diffusion-fa','--vae-tiling','--mmap','--cfg-scale','1.0','--sampling-method','euler','--scheduler',scheduler,'--steps',str(steps),'-t','6','--listen-ip','127.0.0.1','--listen-port','18085']
 (OUT/(name+'-command.json')).write_text(json.dumps(cmd,indent=2))
 monitor_done=threading.Event();fatal=[];current={'label':'loading'};samples=[]
 with (OUT/(name+'-server.log')).open('w') as log:
  start=time.monotonic();p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  def monitor():
   with (OUT/(name+'-telemetry.jsonl')).open('w') as f:
    while not monitor_done.is_set() and p.poll() is None:
     try:
      m=metrics(p.pid);m.update(label=current['label'],elapsed_seconds=round(time.monotonic()-start,3));samples.append(m);f.write(json.dumps(m)+'\n');f.flush()
      if m['gpu_edge_c']>=75 or m['host_available_bytes']<384*1024**2:
       fatal.append('Temperature or memory guard');os.killpg(p.pid,signal.SIGTERM);break
     except FileNotFoundError:break
     except Exception as e:fatal.append(str(e));os.killpg(p.pid,signal.SIGTERM);break
     monitor_done.wait(.5)
  t=threading.Thread(target=monitor,daemon=True);t.start()
  results=[]
  try:
   while True:
    if p.poll() is not None:raise RuntimeError(f'{name} exited during loading: {p.returncode}')
    if time.monotonic()-start>240:raise TimeoutError('model loading')
    try:http('/v1/models',timeout=2);break
    except (OSError,urllib.error.URLError):time.sleep(1)
   load=time.monotonic()-start
   (OUT/(name+'-load.json')).write_text(json.dumps({'ready_seconds':load,'clock':smu()},indent=2))
   jobs=[('smoke',512,'server',42)] if MODE=='smoke' else [(f'{size}-{kind}{rep}',size,'server',41+rep) for size in (512,1024) for rep,kind in ((0,'warmup'),(1,'repeat'),(2,'repeat'),(3,'repeat'))]+[('1024-dungeon',1024,'dungeon',42),('1024-hands',1024,'hands',42)]
   for label,size,prompt,seed in jobs:
    current['label']=label;offset=len(samples);clock=smu()
    if clock['gfx_frequency_mhz']!=args.clock_mhz:raise RuntimeError(f'GPU clock is not {args.clock_mhz} MHz')
    payload={'prompt':PROMPTS[prompt],'width':size,'height':size,'steps':steps,'cfg_scale':1.0,'seed':seed,'batch_size':1,'sampler_name':'Euler','scheduler':scheduler}
    before=time.monotonic();response=http('/sdapi/v1/txt2img',payload);elapsed=time.monotonic()-before
    data=base64.b64decode(response['images'][0].split(',')[-1]);assert data[:8]==b'\x89PNG\r\n\x1a\n';assert struct.unpack('>II',data[16:24])==(size,size)
    filename=f'{name}-{label}.png';(OUT/filename).write_bytes(data)
    row={'model':name,'label':label,'size':size,'prompt_id':prompt,'seed':seed,'steps':steps,'scheduler':scheduler,'wall_seconds':elapsed,'image':filename,'clock_before':clock,'clock_after':smu()}
    subset=samples[offset:]
    if subset:
     row['peaks']={k:(min if k=='host_available_bytes' else max)(r[k] for r in subset) for k in subset[0] if k not in ('label','elapsed_seconds')}
    results.append(row);(OUT/(name+'-results.json')).write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(row),flush=True)
    if fatal:raise RuntimeError(fatal)
  finally:
   monitor_done.set();terminate(p);t.join(3)
   (OUT/(name+'-exit.json')).write_text(json.dumps({'server_exit':p.returncode,'guard_events':fatal,'cgroup_memory_events':(CG/'memory.events').read_text()}))
try:
 if args.chat_service:subprocess.run(['systemctl','stop',args.chat_service],check=True)
 for _ in range(120):
  temp=max(int(p.read_text()) for p in pathlib.Path('/sys/class/drm/card1/device/hwmon').glob('hwmon*/temp1_input'))
  if temp<=60000:break
  time.sleep(1)
 for name in MODELS:model_run(name)
 (OUT/'complete.txt').write_text(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
finally:
 if args.chat_service:subprocess.run(['systemctl','start',args.chat_service])
