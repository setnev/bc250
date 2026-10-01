"""Continuous 24-hour VM-only workload through existing production power profiles.

This is a separate operational profile test, not additional fixed-clock comparison
trials. A completed soak still needs independent transcript review before success
rates or eligibility can be reported.
"""
from pathlib import Path
import argparse, fcntl, hashlib, importlib.util, json, os, queue, signal, threading, time
import agent_core
import soak_api
from fault_proxy import Server
from soak_preflight import validate_smoke
from screening_policy import validate_main

R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('driver',R/'main-agent.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
STOP=threading.Event()

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def kernel_fault_result(result):
    """journalctl returns 1 without diagnostics when a grep has no matches."""
    output=result['stdout'].strip()
    if result['returncode']==0:return bool(output and output!='-- No entries --')
    if (result['returncode']==1 and not result['stderr'].strip()
            and output in ('','-- No entries --')):return False
    raise RuntimeError('Kernel journal query failed: '+result['stderr'][-2000:])

def build_schedule(routine):
    assert routine and len(set(routine))==len(routine)
    schedule=[]
    # Rotate the variant after each case cycle. i % 3 would permanently pair
    # each case with only one variant when the case count is divisible by 3.
    for i in range(288):
        schedule.append({'id':f'routine-{i:03}','kind':'routine','offset':i*300,
                         'case':routine[i%len(routine)],'variant':(i//len(routine))%3})
    for offset,case,variant in [(7200,'F01',0),(28800,'F05',1),(50400,'F07',0),(72000,'F08',0)]:
        schedule.append({'id':f'fault-{case}','kind':'fault','offset':offset+120,'case':case,'variant':variant})
    for offset in (21600,43200,64800):
        for i in range(3):
            schedule.append({'id':f'queue-{offset}-{i}','kind':'queue','offset':offset+120,
                             'case':routine[i%len(routine)],'variant':i})
    return sorted(schedule,key=lambda x:(x['offset'],x['id']))

def telemetry(since_epoch=None):
    hardware=soak_api.json_request('/hardware')
    script="""python3 - <<'PY'
from pathlib import Path
import json,subprocess,time
memory={k:int(v.split()[0]) for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines()) if k in ['MemAvailable','MemFree','SwapFree','SwapTotal']}
units={}
for unit in ['bc250-ai','bc250-api-gateway','bc250-profile-controller','bc250-ops-lab']:
 p=subprocess.run(['systemctl','show',unit,'-p','ActiveState','-p','MainPID','-p','NRestarts'],capture_output=True,text=True,check=True)
 units[unit]=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
 pid=units[unit]['MainPID']
 try:
  status=dict(line.split(':',1) for line in Path('/proc',pid,'status').read_text().splitlines() if ':' in line)
  units[unit]['rss_kib']=int(status.get('VmRSS','0').split()[0])
 except FileNotFoundError:units[unit]['rss_kib']=None
workers=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  if (proc/'comm').read_text().strip()!='llama-server':continue
  status=dict(line.split(':',1) for line in (proc/'status').read_text().splitlines() if ':' in line)
  workers.append({'pid':int(proc.name),'rss_kib':int(status.get('VmRSS','0').split()[0])})
 except (FileNotFoundError,PermissionError):pass
print(json.dumps({'epoch':time.time(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'memory_kib':memory,'services':units,'inference_processes':workers}))
PY
"""
    host=json.loads(driver.host(script,timeout=30))
    if since_epoch is not None:
        query="""python3 - <<'PY'
import json,subprocess
p=subprocess.run(['journalctl','-k','--since','__SINCE__','--grep',
                  'amdgpu.*(reset|fault)|GPU hang|Out of memory|oom-kill',
                  '-o','cat','--no-pager','-n','1'],capture_output=True,text=True)
print(json.dumps({'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}))
PY
""".replace('__SINCE__','@'+str(int(since_epoch)))
        events=json.loads(driver.host(query,timeout=10))
        host['kernel_fault_observed']=kernel_fault_result(events)
    return {'epoch':time.time(),'hardware':hardware,'host':host}

def validate_selection(path):
    selection=json.loads(path.read_text())
    main=R/'main-results';coverage=json.loads((main/'coverage.json').read_text())
    assert coverage['recorded_trials']==1200 and not coverage['stopped']
    grades=json.loads((main/'review/grades.json').read_text())
    assert len(grades)==1200, 'Finish independent review before selecting the soak workload'
    _,screening=validate_main(main)
    assert selection['full_review_sha256']==digest(main/'review/grades.json')
    assert len(selection['rationale'])>=40
    candidate=selection['candidate'];assert candidate in driver.CANDIDATES
    assert candidate not in screening['critical_stops'], 'Critically stopped candidate is ineligible for the soak'
    cases={x['id']:x for x in json.loads((main/'sources/cases.json').read_text())}
    assert selection['routine_cases']
    for case in selection['routine_cases']:
        assert case[0] in 'NSCMBIA' and cases[case]['case_timeout_seconds']==180
        subset=[x for x in grades if x['candidate']==candidate and x['case_id']==case]
        assert len(subset)==3 and all(x['passed'] for x in subset), 'Routine cases must pass all original variants'
    models=soak_api.json_request('/models')['data'];available={x['id'] for x in models}
    required={'qwen3.5-2b','qwen3.5-9b'} if candidate=='worker2b-planner9b' else {candidate}
    assert required<=available, 'Selected soak models must exist in the preserved production gateway'
    return selection,cases

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--selection',type=Path,required=True);args=parser.parse_args()
    lock=(R/'main-runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    selection,cases=validate_selection(args.selection)
    smoke=validate_smoke(R,args.selection,selection)
    folder=R/'soak-results';folder.mkdir(exist_ok=False)
    for name in ('runs','sources'): (folder/name).mkdir()
    names=driver.SOURCES+['soak-bench.py','soak_api.py','analyze-soak.py','capture-soak-runtime.py','soak-projection-manifest.json','soak-runtime-pins.json','production-soak-smoke.py','soak_preflight.py','soak-review.py','message_supplement.py','screening_policy.py']
    import shutil
    for name in names:shutil.copy2(R/name,folder/'sources'/name)
    runtime_spec=importlib.util.spec_from_file_location('soak_runtime',R/'capture-soak-runtime.py')
    runtime_module=importlib.util.module_from_spec(runtime_spec);runtime_spec.loader.exec_module(runtime_module)
    runtime=runtime_module.capture(selection['candidate'])
    driver.atomic(folder/'runtime-configuration.json',runtime)
    started=time.monotonic();epoch=time.time();jobs=queue.Queue();rows=[];samples=[];worker_error=[];state_lock=threading.Lock()
    proxy=Server(18121,'http://127.0.0.1:18123');threading.Thread(target=proxy.serve_forever,daemon=True).start()
    forwarding=soak_api.forwarding_server();agent_core.api=soak_api.api
    initial=telemetry(epoch);host_boot=initial['host']['boot_id'];vm_pid=initial['host']['services']['bc250-ops-lab']['MainPID']
    assert initial['hardware']['cpu']['mode']=='idle' and not initial['hardware']['latched']
    protocol={'duration_seconds':86400,'routine_jobs':288,'interval_seconds':300,'candidate':selection['candidate'],'routine_cases':selection['routine_cases'],'selection':selection,'source_sha256':{n:digest(R/n) for n in names},'transport':'Existing authenticated production gateway, existing per-model profiles, identical bounded VM tools; no production write authorization.','timings':'Queue wait, case execution, scheduled-to-completion, and snapshot overhead recorded separately.','fault_events':{'7200':'F01-v0 SSH drop','28800':'F05-v1 actual two HTTP503 responses','50400':'F07-v0 VM reboot','72000':'F08-v0 SSH worker crash and expired lease'},'queue_bursts_seconds':[21600,43200,64800],'queue_burst_jobs':3,'started_epoch':epoch,'frontier_parity':'uncalibrated','wall_power_watts':None,'acceptance_criteria':{'routine_success_within_case_budget':0.95,'continuous_seconds':86400,'expected_jobs':301,'telemetry_interval_seconds':15,'maximum_telemetry_gap_seconds':60,'idle_release_deadline_seconds':45,'memory_trend':'Report first and final hour medians after first-hour settling; review an RSS increase above max(256MiB,10% of settled RSS) and a monotonic rising trend. Such growth is a failed memory gate unless independently explained as a bounded model-load/cache difference. Host available memory must remain >=512MiB; no host service crash/restart or containment failure.'}}
    protocol['runtime_configuration']=runtime
    protocol['production_gateway_smoke']=smoke
    driver.atomic(folder/'protocol.json',protocol);driver.atomic(folder/'initial-state.json',initial)
    def sample_loop():
        while not STOP.is_set():
            try:
                sample=telemetry(epoch);sample.update(elapsed_seconds=time.monotonic()-started,queue_length=jobs.qsize())
                with state_lock:
                    samples.append(sample)
                    with (folder/'telemetry.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n');f.flush()
                host=sample['host'];hardware=sample['hardware']
                if hardware.get('latched') or hardware['temperature_c']>=85:raise RuntimeError('Production thermal guard or soak temperature threshold reached')
                if host['memory_kib']['MemAvailable']<512*1024:raise RuntimeError('Host memory reserve below512MiB')
                if host['boot_id']!=host_boot or host['services']['bc250-ops-lab']['MainPID']!=vm_pid:raise RuntimeError('Unexpected inference host reboot or VM host process restart')
                if any(x['ActiveState']!='active' for x in host['services'].values()):raise RuntimeError('Required host service inactive')
                if host['kernel_fault_observed']:raise RuntimeError('Host GPU fault or OOM observed')
            except Exception as error:
                with state_lock:worker_error.append({'stage':'telemetry','error':type(error).__name__,'detail':str(error),'epoch':time.time()})
                STOP.set();break
            STOP.wait(15)
    def worker():
        while not STOP.is_set():
            try:job=jobs.get(timeout=1)
            except queue.Empty:continue
            if job is None:jobs.task_done();break
            now=time.monotonic();job_folder=folder/'runs'/job['id'];job_folder.mkdir();(job_folder/'runs').mkdir()
            row={**job,'started_epoch':time.time(),'queue_wait_seconds':now-job['queued_monotonic'],'schedule_delay_seconds':now-(started+job['offset'])}
            try:
                record=driver.evaluate(selection['candidate'],cases[job['case']],job['variant'],job_folder,'soak')
                row.update(status=record['status'],agent_seconds=record.get('agent_seconds'),total_seconds=record['total_seconds'],scheduled_to_completion_seconds=time.monotonic()-(started+job['offset']),independent_checks=record.get('independent_checks'),restoration_verified=record.get('restoration_verified'),critical_containment_failure=record.get('critical_containment_failure'),semantic_review='pending')
                if not record.get('restoration_verified') or record.get('critical_containment_failure'):raise RuntimeError('Soak containment or restoration failure')
            except Exception as error:
                row.update(status='failed',error={'type':type(error).__name__,'detail':str(error)})
                with state_lock:worker_error.append({'stage':'task','job':job['id'],'error':row['error']})
                STOP.set()
            finally:
                row['finished_epoch']=time.time()
                with state_lock:rows.append(row);driver.atomic(folder/'jobs.json',rows)
                print(json.dumps(row),flush=True);jobs.task_done()
    for signum in (signal.SIGINT,signal.SIGTERM):signal.signal(signum,lambda *_:STOP.set())
    sample_thread=threading.Thread(target=sample_loop,daemon=True);sample_thread.start();worker_thread=threading.Thread(target=worker);worker_thread.start()
    schedule=build_schedule(selection['routine_cases']);driver.atomic(folder/'schedule.json',schedule)
    try:
        for job in schedule:
            if STOP.wait(max(0,started+job['offset']-time.monotonic())):break
            queued={**job,'queued_monotonic':time.monotonic(),'queued_epoch':time.time(),'queue_length_on_submission':jobs.qsize()}
            jobs.put(queued)
            with (folder/'queue-events.jsonl').open('a') as f:f.write(json.dumps(queued)+'\n');f.flush()
        STOP.wait(max(0,started+86400-time.monotonic()))
        if not STOP.is_set():
            jobs.put(None);worker_thread.join(timeout=1000)
            if worker_thread.is_alive():worker_error.append({'stage':'completion','error':'Worker failed to drain within its maximum case budget'});STOP.set()
    finally:
        STOP.set();worker_thread.join(timeout=1000);sample_thread.join(timeout=45)
        proxy.shutdown();proxy.server_close();forwarding.shutdown();forwarding.server_close()
        try:
            restore=driver.restore();driver.atomic(folder/'final-snapshot-restoration.json',restore)
        except Exception as error:worker_error.append({'stage':'restoration','error':type(error).__name__,'detail':str(error)})
        import subprocess
        recovery=subprocess.run(['python3',str(R/'check-recovery.py')],capture_output=True,text=True,timeout=60)
        driver.atomic(folder/'production-recovery.json',{'exit_code':recovery.returncode,'stdout':recovery.stdout,'stderr':recovery.stderr})
        try:final=telemetry(epoch);driver.atomic(folder/'final-state.json',final)
        except Exception as error:worker_error.append({'stage':'final_telemetry','error':type(error).__name__,'detail':str(error)})
        routines=[x for x in rows if x['kind']=='routine']
        result={'elapsed_seconds':time.monotonic()-started,'started_epoch':epoch,'finished_epoch':time.time(),'expected_routine_jobs':288,'recorded_routine_jobs':len(routines),'recorded_fault_jobs':sum(x['kind']=='fault' for x in rows),'recorded_queue_jobs':sum(x['kind']=='queue' for x in rows),'missed_routine_start_slots':sum(x['schedule_delay_seconds']>300 for x in routines),'routine_completed_within_scheduled_case_budget':sum(x.get('scheduled_to_completion_seconds',float('inf'))<=cases[x['case']]['case_timeout_seconds'] for x in routines),'errors':worker_error,'telemetry_samples':len(samples),'production_recovery_exit_code':recovery.returncode,'complete':len(routines)==288 and len(rows)==301 and all(x['status']=='completed' and x.get('restoration_verified') and not x.get('critical_containment_failure') for x in rows) and time.monotonic()-started>=86400 and not worker_error and recovery.returncode==0,'semantic_review':'pending; state checks and raw counts do not establish the95percent quality gate','frontier_parity':'uncalibrated'}
        driver.atomic(folder/'completion.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
