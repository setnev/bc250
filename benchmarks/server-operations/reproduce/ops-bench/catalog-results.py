"""Catalog executed trials without inventing semantic grades or frontier parity."""
from pathlib import Path
import json,csv,statistics,hashlib,argparse
import math
R=Path(__file__).resolve().parent
ORDER='NSCMBIAGF'
def percentile(values,p):
 import math
 return sorted(values)[max(0,math.ceil(p*len(values))-1)] if values else None

def inference_performance(events):
 """Aggregate recorded runtime work, retaining absent timing coverage."""
 emitted=[e for e in events if e.get('assistant')]
 result={'recorded_inference_responses':len(emitted),
         'inference_errors':sum(bool(e.get('inference_error')) for e in events)}
 def finite(value):
  return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0
 for label,count_name,time_name in [('decode','predicted_n','predicted_ms'),('uncached_prefill','prompt_n','prompt_ms')]:
  paired=[(e['timings'][count_name],e['timings'][time_name]) for e in emitted
          if isinstance(e.get('timings'),dict) and finite(e['timings'].get(count_name))
          and finite(e['timings'].get(time_name)) and e['timings'][time_name]>0]
  count=sum(x for x,_ in paired);duration=sum(y for _,y in paired)
  result[label]={'responses_with_paired_runtime_timings':len(paired),
                 'responses_without_usable_paired_runtime_timings':len(emitted)-len(paired),
                 'recorded_tokens':count,'recorded_milliseconds':duration,
                 'tokens_per_second_from_totals':1000*count/duration if duration else None}
 first=[e['first_content_or_tool_delta_seconds'] for e in emitted
        if finite(e.get('first_content_or_tool_delta_seconds'))]
 cached=[e['timings']['cache_n'] for e in emitted
         if isinstance(e.get('timings'),dict) and finite(e['timings'].get('cache_n'))]
 result.update(first_content_or_tool_delta_samples=len(first),
               first_content_or_tool_delta_median_seconds=statistics.median(first) if first else None,
               first_content_or_tool_delta_p95_seconds=percentile(first,.95),
               responses_with_cache_count=len(cached),recorded_cached_prompt_tokens=sum(cached))
 return result
def catalog(folder):
 protocol=json.loads((folder/'protocol.json').read_text());case_file=folder/'sources/cases.json'
 cases={x['id']:x for x in json.loads((case_file if case_file.exists() else R/'cases.json').read_text())}
 candidates=protocol['candidates'];records=[]
 for file in (folder/'runs').glob('*.json'):
  r=json.loads(file.read_text());r['_record_sha256']=hashlib.sha256(file.read_bytes()).hexdigest();records.append(r)
 record_by_key={(r['candidate'],r['case_id'],r['variant']):r for r in records}
 if len(record_by_key)!=len(records):raise ValueError('Duplicate trial records')
 grades_file=folder/'review/grades.json';reviewed={}
 for grade in json.loads(grades_file.read_text()) if grades_file.exists() else []:
  key=(grade['candidate'],grade['case_id'],grade['variant'])
  if key in reviewed:raise ValueError('Duplicate review record')
  if key not in record_by_key or grade['record_sha256']!=record_by_key[key]['_record_sha256']:
   raise ValueError('Stale or unknown review evidence')
  reviewed[key]=grade
 records.sort(key=lambda r:(candidates.index(r['candidate']),ORDER.index(r['case_id'][0]),int(r['case_id'][1:]),r['variant']))
 rows=[];reviews=[]
 for r in records:
  case=cases[r['case_id']];events=r.get('events',[]);metrics=[x for x in events if x.get('assistant')];ttft=[x['first_content_or_tool_delta_seconds'] for x in metrics if x.get('first_content_or_tool_delta_seconds') is not None]
  runtime=[x['timings'] for x in metrics if x.get('timings')];decode_n=sum(x.get('predicted_n',0) for x in runtime);decode_ms=sum(x.get('predicted_ms',0) for x in runtime);prefill_n=sum(x.get('prompt_n',0) for x in runtime);prefill_ms=sum(x.get('prompt_ms',0) for x in runtime)
  checks=r.get('independent_checks',{});counters=r.get('counters',{})
  rows.append({'candidate':r['candidate'],'case_id':r['case_id'],'variant':r['variant'],'status':r['status'],'severity':case['ratings']['severity'],'impact':case['ratings']['impact'],'complexity':case['ratings']['complexity'],'criticality':case['ratings']['criticality'],'security':case['ratings']['security'],'risk':case['ratings']['risk'],'risk_weight':case['ratings']['weight'],'agent_seconds':r.get('agent_seconds'),'total_seconds_including_snapshot_recovery':r.get('total_seconds'),'model_turns':counters.get('turns'),'tool_calls':counters.get('tools'),'schema_rejections':counters.get('schema_rejections'),'transport_errors':counters.get('transport_errors'),'inference_errors':counters.get('inference_errors'),'independent_state_outcome':checks.get('state_outcome_passed'),'protected_state_preserved':checks.get('protected_state_preserved'),'restoration_verified':r.get('restoration_verified'),'attempted_unauthorized_writes':r.get('attempted_unauthorized_writes'),'synthetic_secret_disclosed':r.get('synthetic_secret_disclosed'),'ttft_median_seconds':statistics.median(ttft) if ttft else None,'runtime_decode_tokens_per_second':1000*decode_n/decode_ms if decode_ms else None,'runtime_prefill_uncached_tokens_per_second':1000*prefill_n/prefill_ms if prefill_ms else None,'runtime_cached_prompt_tokens':sum(x.get('cache_n',0) for x in runtime),'semantic_review':'pending','record_sha256':r['_record_sha256']})
  review=reviewed.get((r['candidate'],r['case_id'],r['variant']))
  rows[-1]['semantic_review']='sha_bound_review_available' if review else ('screened_unexecuted' if r['status']=='screened_out' else 'pending')
  if r['status']=='completed' and review is None:reviews.append({'candidate':r['candidate'],'case_id':r['case_id'],'variant':r['variant'],'record_sha256':r['_record_sha256'],'status':'pending','required_evidence':['case-specific requirements','agent-visible observations','every final claim','independent observed state','scope/identity/approval behavior','post-write verification and recovery'],'components':{k:None for k in ['diagnosis','plan_scope','execution','verification_recovery','security_policy','reporting']}})
 destination=folder/'catalog';destination.mkdir(exist_ok=True)
 (destination/'trials.json').write_text(json.dumps(rows,indent=2)+'\n')
 if rows:
  with (destination/'trials.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 (destination/'review-queue.json').write_text(json.dumps(reviews,indent=2)+'\n')
 summary=[]
 for candidate in candidates:
  selected=[r for r in rows if r['candidate']==candidate];executed=[r for r in selected if r['status']=='completed'];durations=[r['agent_seconds'] for r in executed if r['agent_seconds'] is not None]
  summary.append({'candidate':candidate,'recorded':len(selected),'executed':len(executed),'expected':len(protocol['cases'])*len(protocol['variants']),'state_outcome_passed':sum(r['independent_state_outcome'] is True for r in executed),'restorations_verified':sum(r['restoration_verified'] is True for r in executed),'median_agent_seconds':statistics.median(durations) if durations else None,'p95_agent_seconds_nearest_rank':percentile(durations,.95),'semantic_qualified_tasks':None,'quality_score':None,'frontier_parity':'uncalibrated','actual_workload_coverage':'unmeasured'})
 (destination/'progress-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
 performance=[]
 for candidate in candidates:
  executed=[r for r in records if r['candidate']==candidate and r['status']=='completed']
  events=[e for r in executed for e in r.get('events',[])]
  stages=sorted({(e.get('model'),e.get('role')) for e in events if e.get('model') and e.get('role')})
  performance.append({'candidate':candidate,'executed_trials':len(executed),
      'expected_trials':len(protocol['cases'])*len(protocol['variants']),
      'all_recorded_stages':inference_performance(events),
      'by_model_and_role':[{'model':model,'role':role,**inference_performance(
          [e for e in events if e.get('model')==model and e.get('role')==role])} for model,role in stages]})
 (destination/'inference-performance.json').write_text(json.dumps({
     'coverage_complete':all(x['executed_trials']==x['expected_trials'] for x in performance),
     'cohort':'All completed trials, including failed tasks, correction turns and planner/worker/fallback stages. Unrecorded failed-request runtime timings are not imputed.',
     'throughput_definition':'Sum of recorded llama.cpp token counts divided by sum of their paired runtime milliseconds; not an arithmetic mean of per-turn rates and not end-to-end task throughput. Prefill excludes cached prompt tokens. Combined-model rate summarizes mixed stages; separate model/role rates are provided.',
     'response_definition':'First nonempty content or tool delta, not necessarily the first tool delta. These main-suite timings include model routing/loading and task histories; separate latency probes measure standardized warm/fresh-process tool emission.',
     'percentile_method':'Nearest rank ceil(0.95*N); absent samples stay absent.',
     'candidates':performance},indent=2)+'\n')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);a=parser.parse_args();catalog(a.folder)
