#!/usr/bin/env python3
"""Timing test only; fixed 32-token outputs intentionally truncate answers."""
import urllib.request,json,time,pathlib,os,argparse
parser=argparse.ArgumentParser(description='Run three identical prompts and a three-turn conversation against a persistent llama-server.')
parser.add_argument('--base-url', required=True, help='Server root URL without /v1')
parser.add_argument('--model', required=True)
parser.add_argument('--output', default='consecutive-results.json')
parser.add_argument('--pid', type=int, help='Optional local llama-server PID for Linux disk-read accounting')
args=parser.parse_args()
base=args.base_url.rstrip('/')
headers={'Content-Type':'application/json'}
if os.environ.get('BC250_API_KEY'):
 headers['Authorization']='Bearer '+os.environ['BC250_API_KEY']
def request(path,payload=None,timeout=180):
 req=urllib.request.Request(base+path,headers=headers,data=None if payload is None else json.dumps(payload).encode())
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
def io():
 try:
  pid=args.pid
  if pid is None:return {}
  return dict((k.strip(),int(v)) for k,v in (l.split(':') for l in pathlib.Path(f'/proc/{pid}/io').read_text().splitlines()))
 except (OSError,ValueError):return {}
start=time.monotonic()
while True:
 try:request('/health',timeout=5);break
 except Exception:
  if time.monotonic()-start>150:raise
  time.sleep(2)
results={'startup_wait_seconds':time.monotonic()-start,'output_token_limit':32,'temperature':0,'ignore_eos':True,'runs':[]}
path=pathlib.Path(args.output)
def run(group,index,messages):
 before=io();t=time.monotonic()
 response=request('/v1/chat/completions',{'model':args.model,'messages':messages,'max_tokens':32,'temperature':0,'seed':42,'cache_prompt':True,'ignore_eos':True})
 elapsed=time.monotonic()-t;after=io()
 result={'group':group,'turn':index,'elapsed_seconds':elapsed,'usage':response.get('usage'),'timings':response.get('timings'),'message':response['choices'][0]['message'],'finish_reason':response['choices'][0].get('finish_reason'),'process_io_delta':{k:after[k]-before[k] for k in before.keys()&after.keys()}}
 results['runs'].append(result);path.write_text(json.dumps(results,indent=2));return result['message']
system={'role':'system','content':'You are a concise Python coding assistant. Provide code directly.'}
prompt={'role':'user','content':'Write a Python function that returns whether a string is a palindrome, ignoring case and spaces.'}
for i in range(1,4):run('identical_prompt',i,[system,prompt])
messages=[system,{'role':'user','content':'Write a Python function that counts word frequencies in a string.'}]
for i,next_prompt in enumerate([None,'Continue the function from where you stopped.','Add a small usage example for this function.'],1):
 if next_prompt:messages.append({'role':'user','content':next_prompt})
 reply=run('conversation',i,messages)
 messages.append({'role':'assistant','content':reply.get('content','')})
print('Completed six consecutive requests')
