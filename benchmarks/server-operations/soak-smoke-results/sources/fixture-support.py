"""Actual Linux fixture helpers for the disposable VM only."""
from pathlib import Path
import json,subprocess,socket,struct,threading,http.server,time
ROOT=Path('/var/lib/ops-lab')

def dns_server():
 sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',1053))
 while True:
  data,peer=sock.recvfrom(4096)
  try:
   pos=12;labels=[]
   while data[pos]:
    n=data[pos];pos+=1;labels.append(data[pos:pos+n].decode());pos+=n
   pos+=1;kind,klass=struct.unpack('!HH',data[pos:pos+4]);question=data[12:pos+4]
   conf=json.loads((ROOT/'dns.json').read_text());name='.'.join(labels)
   if kind==1 and name==conf['name']:
    answer=b'\xc0\x0c'+struct.pack('!HHIH',1,1,30,4)+socket.inet_aton(conf['address'])
    result=data[:2]+struct.pack('!HHHHH',0x8180,1,1,0,0)+question+answer
   else:result=data[:2]+struct.pack('!HHHHH',0x8183,1,0,0,0)+question
   sock.sendto(result,peer)
  except Exception:continue

def backup():
 import sqlite3,hashlib,shutil
 policy=ROOT/'backup-policy.json'
 if policy.exists():
  quota=json.loads(policy.read_text())
  if quota['quota_mib']<quota['required_mib']:raise RuntimeError('Backup destination quota exhausted')
 dest=ROOT/'backups';dest.mkdir(exist_ok=True)
 source=sqlite3.connect(ROOT/'app.db');target=sqlite3.connect(dest/'app.db');source.backup(target);target.close();source.close()
 shutil.copy2(ROOT/'app.json',dest/'app.json')
 shutil.copy2(ROOT/'restore-file.txt',dest/'restore-file.txt')
 hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file() and p.name!='manifest.json'}
 (dest/'manifest.json').write_text(json.dumps({'created_epoch':time.time(),'sha256':hashes,'rpo_seconds':3600,'rto_seconds':120},indent=2))

if __name__=='__main__':
 import sys
 if sys.argv[1]=='dns':dns_server()
 elif sys.argv[1]=='backup':backup()
 elif sys.argv[1]=='cpu':
  while True:sum(i*i for i in range(100000))
 elif sys.argv[1]=='oom':
  data=bytearray(64*1024**2);time.sleep(60)
 else:raise SystemExit('Unknown fixture helper')
