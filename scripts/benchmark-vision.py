"""Sequential vision benchmark. Run with sudo on a dedicated BC250."""
import base64,json,os,pathlib,signal,subprocess,threading,time,urllib.request,urllib.error
ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
BIN=os.environ.get('LLAMA_SERVER','llama-server')
MODELS=[('qwen35-9b',str(ROOT/'models/Qwen3.5-9B-Q4_K_M.gguf'),'Qwen3.5-9B-GGUF--mmproj-F16.gguf'),('qwen35-4b',str(ROOT/'models/Qwen3.5-4B-GGUF--Qwen3.5-4B-Q4_K_M.gguf'),'Qwen3.5-4B-GGUF--mmproj-F16.gguf'),('gemma3-4b',str(ROOT/'models/gemma-3-4b-it-GGUF--gemma-3-4b-it-Q4_K_M.gguf'),'gemma-3-4b-it-GGUF--mmproj-model-f16.gguf')]
URL='http://127.0.0.1:18086'
CASES=json.loads((ROOT/'cases.json').read_text())
CG=pathlib.Path('/sys/fs/cgroup'+pathlib.Path('/proc/self/cgroup').read_text().strip().split('::',1)[1])
def smu():return json.loads(subprocess.check_output(['python3','/usr/local/libexec/bc250-gpu-clock.py'],text=True))
def telemetry(pid):
 mem={x.split(':')[0]:int(x.split()[1])*1024 for x in pathlib.Path('/proc/meminfo').read_text().splitlines()}
 d=pathlib.Path('/sys/class/drm/card1/device')
 rss=[x for x in pathlib.Path(f'/proc/{pid}/status').read_text().splitlines() if x.startswith('VmRSS:')]
 return dict(host_available_bytes=mem['MemAvailable'],process_rss_bytes=int(rss[0].split()[1])*1024 if rss else 0,gpu_edge_c=max(int(p.read_text()) for p in (d/'hwmon').glob('hwmon*/temp1_input'))/1000,gpu_gtt_used_bytes=int((d/'mem_info_gtt_used').read_text()),gpu_vram_used_bytes=int((d/'mem_info_vram_used').read_text()))
def image_message(c):
 data=base64.b64encode((ROOT/'fixtures'/c['image']).read_bytes()).decode()
 return {'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+data}},{'type':'text','text':c['prompt']}]}
def request(messages):
 payload=dict(messages=messages,temperature=0,seed=42,max_tokens=256,stream=True,stream_options={'include_usage':True},cache_prompt=True,timings_per_token=True,chat_template_kwargs={'enable_thinking':False})
 req=urllib.request.Request(URL+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 start=time.monotonic();first=None;answer='';reasoning='';events=[]
 with urllib.request.urlopen(req,timeout=300) as r:
  for raw in r:
   line=raw.decode().strip()
   if not line.startswith('data: '):continue
   if line=='data: [DONE]':break
   event=json.loads(line[6:]);events.append(event)
   for choice in event.get('choices',[]):
    delta=choice.get('delta',{});s=delta.get('content') or '';answer+=s;reasoning+=delta.get('reasoning_content') or ''
    if s and first is None:first=time.monotonic()-start
 elapsed=time.monotonic()-start
 return dict(wall_seconds=elapsed,first_content_seconds=first,answer=answer,reasoning=reasoning,usage=next((e['usage'] for e in reversed(events) if e.get('usage')),None),timings=next((e['timings'] for e in reversed(events) if e.get('timings')),None),finish_reason=next((c['finish_reason'] for e in reversed(events) for c in e.get('choices',[]) if c.get('finish_reason')),None))
def run(name,model,proj):
 cmd=[BIN,'-m',model,'--mmproj',str(ROOT/'models'/proj),'--host','127.0.0.1','--port','18086','-c','8192','-b','128','-ub','128','-t','6','-ngl','99','-fa','on','--parallel','1','--jinja','--reasoning','off','--cache-ram','0','--perf']
 (OUT/(name+'-command.json')).write_text(json.dumps(cmd,indent=2))
 samples=[];fatal=[];done=threading.Event();current=['load'];rows=[]
 with (OUT/(name+'-server.log')).open('w') as log:
  start=time.monotonic();p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  def monitor():
   with (OUT/(name+'-telemetry.jsonl')).open('w') as f:
    while not done.is_set() and p.poll() is None:
     try:
      m=telemetry(p.pid);m.update(label=current[0],elapsed_seconds=time.monotonic()-start);samples.append(m);f.write(json.dumps(m)+'\n');f.flush()
      if m['gpu_edge_c']>=75 or m['host_available_bytes']<384*1024**2:
       fatal.append('75 C temperature or 384 MiB available-memory guard');os.killpg(p.pid,signal.SIGTERM);break
     except FileNotFoundError:break
     except Exception as e:fatal.append(str(e));os.killpg(p.pid,signal.SIGTERM);break
     done.wait(.5)
  t=threading.Thread(target=monitor,daemon=True);t.start()
  try:
   while True:
    if p.poll() is not None:raise RuntimeError('server exited during load')
    if time.monotonic()-start>240:raise TimeoutError('load timeout')
    try:
     with urllib.request.urlopen(URL+'/health',timeout=2) as r:
      if r.status==200:break
    except (OSError,urllib.error.URLError):time.sleep(1)
   (OUT/(name+'-load.json')).write_text(json.dumps({'ready_seconds':time.monotonic()-start,'clock':smu()}))
   def measured(label,messages):
    current[0]=label;offset=len(samples);clock=smu()
    if clock['gfx_frequency_mhz']!=1700:raise RuntimeError('Unexpected clock')
    row=request(messages);row.update(model=name,label=label,clock_before=clock,clock_after=smu())
    subset=samples[offset:]
    row['peaks']={k:(min if k=='host_available_bytes' else max)(r[k] for r in subset) for k in subset[0] if k not in ('label','elapsed_seconds')} if subset else {}
    rows.append(row);(OUT/(name+'-results.json')).write_text(json.dumps(rows,indent=2)+'\n');print(name,label,round(row['wall_seconds'],2),row['answer'][:120],flush=True)
    if fatal:raise RuntimeError(fatal)
    return row
   for c in CASES:
    for i in range(1,4):measured(c['id']+'-repeat'+str(i),[image_message(c)])
   history=[image_message(CASES[0])]
   r=measured('conversation-turn1',history);history.append({'role':'assistant','content':r['answer']})
   history.append({'role':'user','content':'Using the same dashboard, what is the CPU percentage-point difference between worker and web? Reply with one integer.'})
   r=measured('conversation-turn2',history);history.append({'role':'assistant','content':r['answer']})
   history.append({'role':'user','content':'Does the image show a GPU temperature? Reply only YES or NO. Do not guess.'})
   measured('conversation-turn3',history)
  finally:
   done.set()
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(15)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   t.join(3)
   (OUT/(name+'-exit.json')).write_text(json.dumps({'guard_events':fatal,'exit':p.returncode,'memory_events':(CG/'memory.events').read_text()}))
try:
 assert (ROOT/'downloads-complete.txt').exists()
 subprocess.run(['systemctl','stop','bc250-ai.service'],check=True)
 for spec in MODELS:run(*spec)
 (OUT/'complete.txt').write_text(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
finally:subprocess.run(['systemctl','start','bc250-ai.service'],check=True)
