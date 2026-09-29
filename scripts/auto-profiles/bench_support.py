import os,pathlib,json,base64,time,urllib.request,urllib.error
ROOT=pathlib.Path(__file__).resolve().parent
BIN=os.environ.get("LLAMA_SERVER","/opt/bc250-ai/llama.cpp/build/bin/llama-server")
URL="http://127.0.0.1:18086"
CASES=[{'id': 'dashboard', 'prompt': 'Read the dashboard. Return JSON with keys degraded_service, cpu_percent (integer), ram_gb (number), queue_jobs (integer).', 'expected': {'degraded_service': 'worker', 'cpu_percent': 91, 'ram_gb': 5.8, 'queue_jobs': 137}, 'image': 'dashboard.png', 'sha256': '16ba4e78ae208b06075623a922e48a19d1f8ab1da59a8c3f3d074069743fc722'}]
MODELS=[(n,str(ROOT/"models"/w),p) for n,w,p in [['qwen35-9b', 'Qwen3.5-9B-Q4_K_M.gguf', 'Qwen3.5-9B-GGUF--mmproj-F16.gguf'], ['qwen35-4b', 'Qwen3.5-4B-GGUF--Qwen3.5-4B-Q4_K_M.gguf', 'Qwen3.5-4B-GGUF--mmproj-F16.gguf'], ['gemma3-4b', 'gemma-3-4b-it-GGUF--gemma-3-4b-it-Q4_K_M.gguf', 'gemma-3-4b-it-GGUF--mmproj-model-f16.gguf']]]
MANAGED_UNITS=["bc250-api-gateway.service","bc250-profile-controller.service","bc250-ai.service","bc250-gpu-tuning.service"]
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
