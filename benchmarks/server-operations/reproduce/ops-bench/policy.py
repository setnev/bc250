"""Deny-by-default structured tool boundaries independent of model behavior."""
from dataclasses import dataclass
from pathlib import Path
import json,time,hmac,hashlib,secrets
class PolicyError(ValueError):pass
READ_RESOURCES={'interfaces','service','app_config','app_logs','listeners','routes','routes_detail','dns','proxy_config','firewall','tls','resources','disk','permissions','schedules','security_events','sudo_policy','authorized_keys','packages','checksums','backup','accounts','release','limits','capacity_history','runbooks','artifacts','logs','latency'}
RUNBOOKS={'repair_dns','start_application','repair_firewall','repair_bind','repair_proxy','renew_certificate','stop_lab_stress','repair_permissions','repair_schedule','apply_updates','rollback_updates','reboot_lab','rotate_logs','clean_artifacts','expand_data_volume','repair_limits','repair_backup_schedule','restore_file','restore_database','restore_application','repair_backup_quota','create_account','disable_account','rotate_ssh_key','repair_groups','rotate_app_token','deploy_release','rollback_release','restart_application','repair_dependencies'}
@dataclass(frozen=True)
class Scope:
 target:str
 task_id:str
 reads:frozenset
 writes:frozenset
 expires_at:float

class Policy:
 def __init__(self,scope,key=None,clock=time.time):
  self.scope=scope;self.key=key or secrets.token_bytes(32);self.clock=clock;self.used=set()
 def require(self,target,operation,resource):
  if target!=self.scope.target:raise PolicyError('Target is not authorized')
  if self.clock()>self.scope.expires_at:raise PolicyError('Change window expired')
  permitted=self.scope.reads if operation=='read' else self.scope.writes if operation=='write' else frozenset()
  if resource not in permitted:raise PolicyError('Operation is not authorized')
 def issue(self,action,resource,ttl=60):
  self.require(self.scope.target,'write',action)
  data={'target':self.scope.target,'task':self.scope.task_id,'action':action,'resource':resource,'expires':min(self.clock()+ttl,self.scope.expires_at),'nonce':secrets.token_hex(16)}
  raw=json.dumps(data,sort_keys=True,separators=(',',':'));sig=hmac.new(self.key,raw.encode(),hashlib.sha256).hexdigest()
  return json.dumps({'grant':data,'signature':sig},separators=(',',':'))
 def consume(self,token,target,action,resource):
  self.require(target,'write',action)
  try:
   v=json.loads(token);g=v['grant'];raw=json.dumps(g,sort_keys=True,separators=(',',':'));sig=hmac.new(self.key,raw.encode(),hashlib.sha256).hexdigest()
   if not hmac.compare_digest(sig,v['signature']):raise PolicyError('Invalid grant signature')
   if (g['target'],g['task'],g['action'],g['resource'])!=(target,self.scope.task_id,action,resource):raise PolicyError('Grant scope mismatch')
   if g['expires']<self.clock():raise PolicyError('Grant expired')
   if g['nonce'] in self.used:raise PolicyError('Grant was already used')
   self.used.add(g['nonce'])
  except (KeyError,TypeError,json.JSONDecodeError) as e:raise PolicyError('Malformed grant') from e

def arguments(value,required,optional=()):
 if not isinstance(value,dict):raise PolicyError('Arguments must be an object')
 if set(value)-set(required)-set(optional) or not set(required)<=set(value):raise PolicyError('Argument names do not match schema')
 if any(not isinstance(value[k],str) for k in required):raise PolicyError('Required arguments must be strings')
 return value

def safe_path(root,relative):
 if not isinstance(relative,str) or '\x00' in relative:raise PolicyError('Invalid path')
 p=Path(relative)
 if p.is_absolute() or '..' in p.parts:raise PolicyError('Path traversal denied')
 base=Path(root).resolve();result=(base/p).resolve()
 if not result.is_relative_to(base):raise PolicyError('Path escapes approved root')
 return result
