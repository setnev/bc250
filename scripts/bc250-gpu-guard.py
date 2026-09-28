#!/usr/bin/python3
"""Hold a qualified GPU clock; release overrides on exit or thermal trouble."""
import glob,json,pathlib,subprocess,sys,time
CONTROL='/usr/local/libexec/bc250-gpu-clock.py'
TARGET=int(sys.argv[1])
assert TARGET in (1600,1700)
def control(*args):
 return json.loads(subprocess.check_output(['/usr/bin/python3',CONTROL,*args],text=True,timeout=5))
try:
 baseline=control('restore')
 if baseline['gfx_frequency_mhz']!=1500 or baseline['gfx_voltage_mv']!=925:
  raise RuntimeError(f'Baseline changed; refusing profile: {baseline}')
 sensors=glob.glob('/sys/class/drm/card*/device/hwmon/hwmon*/temp1_input')
 if not sensors or max(int(pathlib.Path(f).read_text()) for f in sensors)>=75000:
  raise RuntimeError('GPU sensor missing or temperature already at cutoff')
 actual=control(str(TARGET))
 if actual['gfx_frequency_mhz']!=TARGET or actual['gfx_voltage_mv']!=925:
  raise RuntimeError(f'Profile readback mismatch: {actual}')
 print(json.dumps({'profile':actual,'thermal_cutoff_c':75}),flush=True)
 ticks=0
 while True:
  sensors=glob.glob('/sys/class/drm/card*/device/hwmon/hwmon*/temp1_input')
  if not sensors:raise RuntimeError('GPU temperature sensor missing')
  peak=max(int(pathlib.Path(f).read_text()) for f in sensors)
  if peak>=75000:raise RuntimeError(f'GPU thermal cutoff: {peak/1000} C')
  if ticks%30==0:
   actual=control()
   if actual['gfx_frequency_mhz']!=TARGET or actual['gfx_voltage_mv']!=925:
    raise RuntimeError(f'GPU settings changed: {actual}')
  ticks+=1
  time.sleep(1)
finally:
 control('restore')
