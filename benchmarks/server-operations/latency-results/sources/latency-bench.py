"""Twenty warm and ten fresh-process tool-call latency probes per model."""
from pathlib import Path
import json,urllib.request,urllib.error,time,importlib.util,hashlib,statistics
from agent_core import api,TOOLS
from task_inputs import COMMON
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('driver',R/'main-agent.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
def router(path,data=None):
 req=urllib.request.Request('http://127.0.0.1:18120'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as res:return json.load(res)
def unload_all():
 before=router('/models');results=[]
 for model in driver.MODELS:
  try:results.append({'model':model,'response':router('/models/unload',{'model':model})})
  except urllib.error.HTTPError as e:
   if e.code!=400:raise
   results.append({'model':model,'already_not_running':True,'status':e.code})
 return {'before':before,'operations':results,'after':router('/models')}
def probe(model):
 payload={'model':model,'messages':[{'role':'system','content':COMMON},{'role':'user','content':'Read only: inspect the service state on lab-01. Emit exactly one inspect tool call with resource service, then stop. No writes are authorized.'}],'tools':TOOLS,'tool_choice':'auto','temperature':0,'seed':42,'max_tokens':128}
 return api(payload,180)
def main():
 folder=R/'latency-results';folder.mkdir(exist_ok=True);rows=json.loads((folder/'trials.json').read_text()) if (folder/'trials.json').exists() else []
 manifest={'models':driver.MODELS,'warm_per_model':20,'fresh_load_per_model':10,'fresh_definition':'All router model subprocesses unloaded; next request includes process and model load. OS filesystem page cache retained. This is not an SSD cold-cache test.','warm_definition':'An unscored priming request precedes20repeated identical prompts with the same resident model. Report cached prompt counts; this deliberately measures prefix reuse.','metric':'Measured seconds from HTTP request to first nonempty content/tool delta; includes load, scheduling and prefill. Runtime prompt/decode timings are separate.','context':8192,'threads':6,'max_tokens':128,'source_sha256':{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in driver.SOURCES+['latency-bench.py','analyze-latency.py']},'model_hashes':json.loads((R/'model-manifest-draft.json').read_text())}
 if (folder/'protocol.json').exists():assert json.loads((folder/'protocol.json').read_text())==manifest
 else:driver.atomic(folder/'protocol.json',manifest)
 import shutil
 (folder/'sources').mkdir(exist_ok=True)
 for name,digest in manifest['source_sha256'].items():
  archived=folder/'sources'/name
  if archived.exists():assert hashlib.sha256(archived.read_bytes()).hexdigest()==digest
  else:shutil.copy2(R/name,archived)
 window=driver.Window(folder)
 try:
  for model in driver.MODELS:
   window.ensure();unload_all();prime,prime_metrics=probe(model);driver.atomic(folder/(model+'-prime.json'),{'unscored':True,'output':prime,'metrics':prime_metrics})
   for condition,count in [('warm',20),('fresh_load',10)]:
    for i in range(count):
     if any(x['model']==model and x['condition']==condition and x['trial']==i for x in rows):continue
     unloaded=unload_all() if condition=='fresh_load' else None
     start=time.time()
     try:output,metrics=probe(model);row={'model':model,'condition':condition,'trial':i,'started_epoch':start,'status':'completed','output':output,'metrics':metrics,'unload_evidence':unloaded}
     except Exception as e:row={'model':model,'condition':condition,'trial':i,'started_epoch':start,'status':'failed','error':{'type':type(e).__name__,'detail':str(e)},'unload_evidence':unloaded}
     rows.append(row);driver.atomic(folder/'trials.json',rows);print(json.dumps({k:v for k,v in row.items() if k not in ['output','unload_evidence']}),flush=True)
 finally:window.close()
 summary=[]
 for model in driver.MODELS:
  for condition in ['warm','fresh_load']:
   subset=[x for x in rows if x['model']==model and x['condition']==condition];values=sorted(x['metrics']['first_content_or_tool_delta_seconds'] for x in subset if x['status']=='completed' and x['metrics']['first_content_or_tool_delta_seconds'] is not None)
   summary.append({'model':model,'condition':condition,'recorded':len(subset),'valid_first_delta_samples':len(values),'median_seconds':statistics.median(values) if values else None,'p95_seconds_nearest_rank':values[max(0,__import__('math').ceil(.95*len(values))-1)] if values else None,'failures':sum(x['status']=='failed' for x in subset)})
 driver.atomic(folder/'summary.json',summary)
 analysis_spec=importlib.util.spec_from_file_location('latency_analysis',R/'analyze-latency.py')
 analysis=importlib.util.module_from_spec(analysis_spec);analysis_spec.loader.exec_module(analysis)
 driver.atomic(folder/'tool-latency-summary.json',analysis.analyze(rows,driver.MODELS))
if __name__=='__main__':main()
