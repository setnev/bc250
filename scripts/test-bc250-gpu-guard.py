import runpy,unittest.mock as m,json
from pathlib import Path
script=Path(__file__).with_name('bc250-gpu-guard.py')
for case in ('hot_at_start','overheat_running','sensor_failure','clock_mismatch'):
 calls=[]
 def control(cmd,**kw):
  action=cmd[2:] or ['read'];calls.append(action[0])
  mhz=1500 if action[0]=='restore' else 1700
  if case=='clock_mismatch' and action[0]=='1700':mhz=1500
  return json.dumps({'gfx_frequency_mhz':mhz,'gfx_voltage_mv':925})
 temps=iter([75000] if case=='hot_at_start' else [60000,75000])
 def read(*args,**kw):
  if case=='sensor_failure':raise OSError('missing sensor')
  return str(next(temps))
 with m.patch('sys.argv',[str(script),'1700']),m.patch('subprocess.check_output',side_effect=control),m.patch('glob.glob',return_value=['/fake/temp']),m.patch('pathlib.Path.read_text',side_effect=read):
  try:runpy.run_path(str(script),run_name='__main__')
  except (RuntimeError,OSError):pass
  else:raise AssertionError('guard should have stopped')
 assert calls[-1]=='restore',calls
 if case=='hot_at_start':assert '1700' not in calls
 print(case,'PASS: override released')
