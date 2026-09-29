import pathlib,time,json,statistics
R=pathlib.Path('/sys/devices/system/cpu')
def snapshot():
 return {str(p.relative_to(R)):int(p.read_text()) for p in R.glob('cpu[0-9]*/cpuidle/state*/time')}
a=snapshot();t=time.monotonic();time.sleep(30);dt=time.monotonic()-t;b=snapshot()
states={}
for k,v in b.items():
 name=(R/k).parent.joinpath('name').read_text().strip();states[name]=states.get(name,0)+v-a[k]
lat=[]
for _ in range(100):
 t=time.monotonic();time.sleep(.02);lat.append(max(0,(time.monotonic()-t-.02)*1e6))
print(json.dumps({'duration_s':dt,'logical_cpus':16,'idle_residency_percent':{k:100*v/(dt*1e6*16) for k,v in states.items()},'timer_overshoot_us':{'median':statistics.median(lat),'p95':sorted(lat)[94],'max':max(lat)},'frequency_khz':{p.name:(p/'cpuinfo_cur_freq').read_text().strip() for p in R.joinpath('cpufreq').glob('policy*')},'wall_watts':None},indent=2))
