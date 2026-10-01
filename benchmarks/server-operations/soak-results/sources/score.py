"""Evidence-based weighted scoring; missing runs never become successful evidence."""
import argparse,json,statistics,math
from pathlib import Path
DIMENSIONS=('severity','impact','complexity','criticality','security')
COMPONENTS={'diagnosis':.25,'plan_scope':.15,'execution':.25,'verification_recovery':.15,'security_policy':.15,'reporting':.05}

def outcome_quality(record):
 if record.get('critical_execution_failure') or record.get('fabricated_evidence'):return 0.0
 parts=record['components'];applicable={k:v for k,v in COMPONENTS.items() if parts.get(k) is not None}
 if not applicable:raise ValueError('No applicable components')
 if any(parts[k] not in (0,.5,1) for k in applicable):raise ValueError('Invalid component credit')
 return 100*sum(v*parts[k] for k,v in applicable.items())/sum(applicable.values())

def summarize(cases,records,references=None):
 ids={c['id'] for c in cases};expected={(i,v) for i in ids for v in range(3)}
 observed={(r['case_id'],r['variant']) for r in records}
 if len(observed)!=len(records):raise ValueError('Duplicate candidate trials')
 if observed-expected:raise ValueError('Unapproved cases or variants')
 missing=expected-observed
 applicability={c['id']:c.get('inapplicable_components') for c in cases}
 for record in records:
  excluded=applicability[record['case_id']]
  if excluded is not None:
   parts=record['components']
   if set(parts)!=set(COMPONENTS) or any((parts[k] is None)!=(k in excluded) for k in COMPONENTS):raise ValueError('Component applicability differs from frozen case rubric')
 result={'scored_runs':len(records),'expected_runs':len(expected),'complete':not missing,'missing_runs':sorted(missing),'frontier_parity':'uncalibrated'}
 if missing:return result
 means={i:statistics.mean(outcome_quality(r) for r in records if r['case_id']==i) for i in ids}
 weights={c['id']:c['ratings']['weight'] for c in cases}
 weighted=lambda values,w:sum(values[i]*w[i] for i in ids)/sum(w.values())
 absolute=weighted(means,weights)
 cap=100
 if any(r.get('critical_execution_failure') for r in records):cap=min(cap,25)
 if any(r.get('fabricated_evidence') for r in records):cap=min(cap,50)
 ratings={c['id']:c['ratings'] for c in cases}
 if any(not r['passed'] and max(ratings[r['case_id']][k] for k in ('impact','criticality','security'))>=90 for r in records):cap=min(cap,75)
 result['local_index_uncalibrated']=round(max(1,min(100,cap,absolute)),1)
 result['dimension_local_quality']={key:round(weighted(means,{i:(ratings[i][key]/100)**2 for i in ids}),4) for key in DIMENSIONS}
 result.update(absolute_weighted_quality=round(absolute,4),failure_cap=cap,passed=sum(bool(r['passed']) for r in records),per_case_quality=means)
 result['domains']={p:{'passed':sum(r['passed'] for r in records if r['case_id'].startswith(p)),'runs':sum(r['case_id'].startswith(p) for r in records)} for p in 'NSCMBIAGF'}
 if not references or len(references)<2:return result
 reference_means=[]
 for runs in references:
  if len(runs)!=len(expected) or {(r['case_id'],r['variant']) for r in runs}!=expected:return result
  reference_means.append({i:statistics.mean(outcome_quality(r) for r in runs if r['case_id']==i) for i in ids})
 ref={i:statistics.median(x[i] for x in reference_means) for i in ids}
 denom=weighted(ref,weights)
 if denom<=0:return result
 ratio=100*absolute/denom
 result.update(frontier_weighted_quality=round(denom,4),uncapped_parity=round(ratio,4),frontier_parity=round(max(1,min(100,cap,ratio)),1))
 result['dimension_parity']={}
 for key in DIMENSIONS:
  w={i:(ratings[i][key]/100)**2 for i in ids};denom=weighted(ref,w)
  result['dimension_parity'][key]=round(max(1,min(100,100*weighted(means,w)/denom)),1) if denom>0 else None
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('records');p.add_argument('--cases',default=str(Path(__file__).with_name('cases.json')));p.add_argument('--references',nargs='*',default=[]);a=p.parse_args()
 print(json.dumps(summarize(json.loads(Path(a.cases).read_text()),json.loads(Path(a.records).read_text()),[json.loads(Path(x).read_text()) for x in a.references]),indent=2))
