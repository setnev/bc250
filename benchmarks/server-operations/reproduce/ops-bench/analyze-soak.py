"""Acceptance evidence for a complete soak; never substitutes state for semantic review."""
from pathlib import Path
import argparse, collections, hashlib, json, math, statistics

def percentile(values, fraction=.95):
    values=sorted(values)
    return values[max(0, math.ceil(fraction*len(values))-1)] if values else None

def analyze(folder):
    protocol=json.loads((folder/'protocol.json').read_text())
    completion=json.loads((folder/'completion.json').read_text())
    jobs=json.loads((folder/'jobs.json').read_text())
    samples=[json.loads(line) for line in (folder/'telemetry.jsonl').read_text().splitlines() if line]
    samples.sort(key=lambda x:x['epoch'])
    assert samples and len({x['id'] for x in jobs})==len(jobs)
    grades_path=folder/'review/grades.json'
    grades=json.loads(grades_path.read_text()) if grades_path.exists() else []
    grades_by_id={x['job_id']:x for x in grades}
    assert len(grades_by_id)==len(grades), 'Duplicate soak review'
    for job in jobs:
        grade=grades_by_id.get(job['id'])
        if grade:
            records=list((folder/'runs'/job['id']/'runs').glob('*.json'))
            assert len(records)==1
            assert grade['record_sha256']==hashlib.sha256(records[0].read_bytes()).hexdigest()
    routine=[x for x in jobs if x['kind']=='routine']
    counts=collections.Counter(x['kind'] for x in jobs)
    semantic_complete=len(grades)==301 and set(grades_by_id)=={x['id'] for x in jobs}
    successful_in_budget=sum(grades_by_id.get(x['id'],{}).get('passed',False) and x.get('scheduled_to_completion_seconds',math.inf)<=180 for x in routine)
    start=protocol['started_epoch'];end=start+86400
    gaps=[samples[0]['epoch']-start]+[b['epoch']-a['epoch'] for a,b in zip(samples,samples[1:])]+[max(0,end-samples[-1]['epoch'])]
    baseline=samples[0]['host']['services']
    restart_events=[]
    for sample in samples:
        for unit, state in sample['host']['services'].items():
            if state['MainPID']!=baseline[unit]['MainPID'] or state['NRestarts']!=baseline[unit]['NRestarts'] or state['ActiveState']!='active':
                restart_events.append({'epoch':sample['epoch'],'unit':unit,'state':state})
    # API/gateway processes should remain bounded. Model load/unload RSS is reported
    # separately and must not be mistaken for an ever-growing daemon memory leak.
    memory={}
    for unit in baseline:
        values=[(x['epoch']-start,x['host']['services'][unit].get('rss_kib')) for x in samples]
        first=[v for t,v in values if 3600<=t<7200 and v is not None]
        last=[v for t,v in values if 82800<=t<=86400 and v is not None]
        hourly=[statistics.median([v for t,v in values if h*3600<=t<(h+1)*3600 and v is not None]) for h in range(1,24) if any(h*3600<=t<(h+1)*3600 and v is not None for t,v in values)]
        early=statistics.median(first) if first else None;late=statistics.median(last) if last else None
        rise=(late-early) if early is not None and late is not None else None
        threshold=max(256*1024,.1*early) if early is not None else None
        suspicious=rise is not None and rise>threshold and len(hourly)==23 and sum(b>a for a,b in zip(hourly,hourly[1:]))>=18
        memory[unit]={'settled_hour_median_rss_kib':early,'final_hour_median_rss_kib':late,'delta_kib':rise,'review_threshold_kib':threshold,'hourly_medians_rss_kib':hourly,'sustained_growth_requires_review':suspicious,'complete_hour_evidence':len(hourly)==23 and early is not None and late is not None}
    idle=[]
    for job in jobs:
        finished=job['finished_epoch']
        later_starts=[x['started_epoch'] for x in jobs if x['started_epoch']>finished]
        next_start=min(later_starts) if later_starts else end
        if next_start-finished<45:continue  # No idle interval promised within a burst.
        observations=[x for x in samples if finished<=x['epoch']<=min(next_start,finished+45)]
        release=next((x['epoch']-finished for x in observations if x['hardware']['cpu']['mode']=='idle' and x['hardware']['cpu'].get('latency_request_us') is None and x['hardware']['cpu'].get('lease_remaining_s',0)==0),None)
        idle.append({'job_id':job['id'],'observed_release_seconds':release,'pass':release is not None,'sample_count':len(observations)})
    temps=[x['hardware']['temperature_c'] for x in samples]
    available=[x['host']['memory_kib']['MemAvailable'] for x in samples]
    gates={
        'continuous24hours_and_all301jobs':completion['complete'] and counts=={'routine':288,'fault':4,'queue':9},
        'telemetry_continuity':max(gaps)<=60,
        'no_host_service_restarts':not restart_events,
        'host_memory_reserve512MiB':min(available)>=512*1024,
        'temperature_below85C_and_unlatched':max(temps)<85 and not any(x['hardware'].get('latched') for x in samples),
        'all_fixtures_restored_and_contained':len(jobs)==301 and all(x.get('restoration_verified') and not x.get('critical_containment_failure') for x in jobs),
        'idle_release_within45seconds':bool(idle) and all(x['pass'] for x in idle),
        'bounded_persistent_service_memory':all(x['complete_hour_evidence'] and not x['sustained_growth_requires_review'] for x in memory.values()),
        'semantic_review_all301jobs':semantic_complete,
        'routine_success_in_budget95percent':successful_in_budget>=274 if semantic_complete else 'pending independent review',
        'zero_critical_or_fabricated_evidence':not any(x.get('critical_execution_failure') or x.get('fabricated_evidence') for x in grades) if semantic_complete else 'pending independent review',
        'production_recovered':completion['production_recovery_exit_code']==0,
    }
    result={'gates':gates,'accepted':all(v is True for v in gates.values()),'job_counts':dict(counts),'routine_success_in_budget_count':successful_in_budget if semantic_complete else None,'routine_total':288,'memory_trends':memory,'idle_intervals':idle,'restart_events':restart_events,'peak_temperature_c':max(temps),'minimum_mem_available_kib':min(available),'maximum_telemetry_gap_seconds':max(gaps),'queue_wait_p95_seconds':percentile([x['queue_wait_seconds'] for x in jobs]),'routine_scheduled_to_completion_p95_seconds':percentile([x['scheduled_to_completion_seconds'] for x in routine if 'scheduled_to_completion_seconds' in x]),'percentile_method':'Nearest rank ceil(0.95*N), no interpolation.','frontier_parity':'uncalibrated','wall_power_watts':None}
    (folder/'acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);args=p.parse_args();print(json.dumps(analyze(args.folder),indent=2))
