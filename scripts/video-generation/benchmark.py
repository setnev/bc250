"""Pinned Wan comparison on one BC250; isolated API downtime with restoration."""
import pathlib,json,subprocess,time,os,signal,hashlib,sys
R=pathlib.Path(__file__).parent;O=R/'results';O.mkdir(exist_ok=True)
BIN='/opt/bc250-mod-prep/image-bench/build/bin/sd-cli'
CLOCK='/usr/local/libexec/bc250-profile-clock.py'
SERVICES=['bc250-profile-controller.service','bc250-ai.service','bc250-api-gateway.service']
MODELS={'wan21':('wan2.1_t2v_1.3B_fp16.safetensors','wan_2.1_vae.safetensors'),'wan22':('Wan2.2-TI2V-5B-Q4_K_M.gguf','wan2.2_vae.safetensors')}
PROMPTS={'car':'A small red toy car drives smoothly from left to right across a wooden table. The camera stays fixed. Soft daylight, realistic textures, continuous clear motion.','water':'A small waterfall flows continuously over mossy rocks in a green forest. Leaves sway gently in the breeze. The camera slowly moves forward. Natural daylight, realistic water, smooth coherent motion.'}
NEGATIVE='blurry, low quality, distorted, static image, flickering, subtitles, watermark, text'
trials=[];child=None

def clock(*args):return json.loads(subprocess.check_output(['python3',CLOCK,*map(str,args)],text=True,timeout=10))
def telemetry():
 temps=list(pathlib.Path('/sys/class/drm').glob('card*/device/hwmon/hwmon*/temp1_input'))
 if not temps:raise RuntimeError('Missing temperature sensor')
 mem=dict((a.rstrip(':'),int(b)*1024) for a,b,*_ in (x.split() for x in pathlib.Path('/proc/meminfo').read_text().splitlines()))
 out={'monotonic':time.monotonic(),'gpu_edge_c':max(int(p.read_text())/1000 for p in temps),'host_available_bytes':mem['MemAvailable']}
 if child and child.poll() is None:
  try:
   lines=pathlib.Path(f'/proc/{child.pid}/status').read_text().splitlines()
   out['rss_bytes']=next(int(x.split()[1])*1024 for x in lines if x.startswith('VmRSS:'))
  except (FileNotFoundError,StopIteration):pass
 return out
def stop_child():
 global child
 if child and child.poll() is None:
  os.killpg(child.pid,signal.SIGTERM)
  try:child.wait(10)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
 child=None

def run(model,prompt,width,height,frames,steps,label):
 global child
 folder=O/label;folder.mkdir(exist_ok=True)
 deadline=time.monotonic()+600
 while telemetry()['gpu_edge_c']>55:
  if time.monotonic()>deadline:raise RuntimeError('Board did not cool to 55 C')
  time.sleep(5)
 weights,vae=MODELS[model];video=folder/'raw.avi'
 cmd=[BIN,'-M','vid_gen','--diffusion-model',str(R/'models'/weights),'--vae',str(R/'models'/vae),'--t5xxl',str(R/'models/umt5-xxl-encoder-Q4_K_M.gguf'),'-p',PROMPTS[prompt],'-n',NEGATIVE,'--cfg-scale','6','--sampling-method','euler','--steps',str(steps),'--flow-shift','3','-W',str(width),'-H',str(height),'--video-frames',str(frames),'--fps','16','--diffusion-fa','--vae-tiling','--temporal-tiling','--offload-to-cpu','--mmap','-t','6','-s','42','-o',str(video)]
 (folder/'command.json').write_text(json.dumps(cmd,indent=2))
 samples=[];fault=None;before=clock();start=time.monotonic()
 with (folder/'runtime.log').open('w') as log,(folder/'telemetry.jsonl').open('w') as trace:
  child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  while child.poll() is None:
   sample=telemetry();samples.append(sample);trace.write(json.dumps(sample)+'\n');trace.flush()
   if sample['gpu_edge_c']>=85:fault='85 C cutoff'
   if sample['host_available_bytes']<384*1024**2:fault='host memory reserve'
   if time.monotonic()-start>3600:fault='3600 second trial timeout'
   if fault:stop_child();break
   time.sleep(.5)
  code=child.returncode if child else None
 elapsed=time.monotonic()-start;stop_child()
 result={'label':label,'model':model,'prompt_id':prompt,'width':width,'height':height,'requested_frames':frames,'steps':steps,'seed':42,'playback_fps':16,'process_seconds':elapsed,'exit_code':code,'fault':fault,'clock_before':before,'clock_after':clock(),'peak_edge_c':max(x['gpu_edge_c'] for x in samples),'minimum_available_bytes':min(x['host_available_bytes'] for x in samples),'peak_rss_bytes':max(x.get('rss_bytes',0) for x in samples)}
 if code==0 and video.exists():
  mp4=folder/'clip.mp4'
  t=time.monotonic();subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),'-map_metadata','-1','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(mp4)],check=True)
  result['mp4_encode_seconds']=time.monotonic()-t
  probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(mp4)],text=True));probe['format'].pop('filename',None)
  (folder/'ffprobe.json').write_text(json.dumps(probe,indent=2))
  stream=probe['streams'][0];count=int(stream['nb_read_frames'])
  assert count==frames and stream['width']==width and stream['height']==height,(label,stream)
  result.update(validated_frames=count,generated_frames_per_second=count/elapsed,mp4_sha256=hashlib.sha256(mp4.read_bytes()).hexdigest())
  hashes=subprocess.check_output(['ffmpeg','-v','error','-i',str(video),'-f','framemd5','-'],text=True)
  (folder/'frames.md5').write_text(hashes)
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(mp4),'-vf','select=eq(n\\,0)+eq(n\\,8)+eq(n\\,16)+eq(n\\,24)+eq(n\\,32),scale=256:-1,tile=5x1','-frames:v','1',str(folder/'contact.png')],check=True)
 trials.append(result);(O/'trials.json').write_text(json.dumps(trials,indent=2));print(json.dumps(result),flush=True)
 if fault:raise RuntimeError(fault)
 return code==0 and video.exists()

def interrupted(*_):raise RuntimeError('Benchmark interrupted')
signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
assert (R/'download-complete.txt').exists()
assert not (R/'restore-state.json').exists(),'Unrestored previous run'
state={'services':[s for s in SERVICES if subprocess.run(['systemctl','is-active','--quiet',s]).returncode==0],'cpu_governors':{str(p):p.read_text().strip() for p in pathlib.Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_governor')}}
(R/'restore-state.json').write_text(json.dumps(state));(O/'protocol.json').write_text(json.dumps({'prompts':PROMPTS,'negative_prompt':NEGATIVE,'models':MODELS,'cpu_governor':'performance','cpu_threads':6,'gpu_mhz':1200,'gpu_vid':100,'cooldown_c':55,'cutoff_c':85,'runtime':BIN},indent=2))
try:
 subprocess.run(['systemctl','stop','bc250-api-gateway.service','bc250-ai.service','bc250-profile-controller.service'],check=True)
 clock('set',1200,100)
 for path in state['cpu_governors']:pathlib.Path(path).write_text('performance')
 qualified=[]
 for model in MODELS:
  if run(model,'car',256,160,17,4,model+'-smoke'):qualified.append(model)
 for model in qualified:
  for prompt,repeat in [('car',1),('car',2),('water',1)]:run(model,prompt,512,288,33,20,f'{model}-{prompt}-{repeat}')
 for model in qualified:run(model,'car',832,480,33,20,model+'-480p')
 (O/'complete.json').write_text(json.dumps({'qualified_models':qualified,'trials':len(trials)}))
finally:
 stop_child();subprocess.run(['python3',str(R/'restore.py')],check=True)
