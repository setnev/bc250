# Restricted frequency experiment and SMU queries adapted from bc250-collective governor e9201068.
# Uses SMU queries plus restricted frequency/VID override and release commands.
# Adapted from bc250-collective/cyan-skillfish-governor e9201068; see SMU-LICENSE.
import os,struct,fcntl,json,time,sys
fd=os.open('/sys/bus/pci/devices/0000:00:00.0/config',os.O_RDWR)
fcntl.flock(fd,fcntl.LOCK_EX)
def write(reg,value):
 os.pwrite(fd,struct.pack('<I',reg),0xb8);os.pwrite(fd,struct.pack('<I',value),0xbc)
def read(reg):
 os.pwrite(fd,struct.pack('<I',reg),0xb8);return struct.unpack('<I',os.pread(fd,4,0xbc))[0]
def query(cmd,rsp,arg,msg,value=0):
 write(rsp,0);write(arg,value);write(arg+4,0);write(cmd,msg)
 deadline=time.monotonic()+.5
 while time.monotonic()<deadline:
  status=read(rsp)
  if status==1:return read(arg)
  if status in (255,254,253,252):raise RuntimeError(f'SMU response {status}')
 raise TimeoutError('SMU query timed out')
assert query(0x03b10a20,0x03b10a80,0x03b10a88,1,123)==124
if len(sys.argv)>1:
 action=sys.argv[1]
 if action in ('1200',):
  query(0x03b10a08,0x03b10a68,0x03b10a48,0x3b,100) # retain baseline VID: 925 mV
  query(0x03b10a08,0x03b10a68,0x03b10a48,0x39,int(action))
 elif action=='restore':
  query(0x03b10a08,0x03b10a68,0x03b10a48,0x3a)
  time.sleep(0.5)
  query(0x03b10a08,0x03b10a68,0x03b10a48,0x3c)
 else:raise ValueError('Only 1200 MHz or restore are permitted')
 time.sleep(0.5)
freq=query(0x03b10a08,0x03b10a68,0x03b10a48,0x37)
vid=query(0x03b10a08,0x03b10a68,0x03b10a48,0x38)
print(json.dumps({'gfx_frequency_mhz':freq,'gfx_vid':vid,'gfx_voltage_mv':round(1550-vid*6.25)}))
os.close(fd)
