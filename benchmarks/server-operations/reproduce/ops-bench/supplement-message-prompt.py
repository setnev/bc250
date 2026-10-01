"""A06 prompt clarification; original grades and 80-case index remain intact."""
from pathlib import Path
import copy, fcntl, hashlib, importlib.util, json, shutil, signal
import agent_core
from message_supplement import corrected_source

R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('driver',R/'main-agent.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def clarified_inputs():
    spec=importlib.util.spec_from_file_location('clarified_inputs',R/'message-prompt-supplement/task_inputs.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def main():
    coverage=json.loads((R/'main-results/coverage.json').read_text())
    assert coverage['recorded_trials']==1200 and not coverage['stopped']
    assert json.loads((R/'after-comparison-state.json').read_text())['status'].startswith('latency_completed')
    lock=(R/'main-runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    base=json.loads((R/'main-results/protocol.json').read_text())
    from screening_policy import critical_stops, screening_record
    stopped_candidates=critical_stops(R/'main-results')
    assert all(digest(R/name)==pin for name,pin in base['source_sha256'].items()), 'Frozen main sources changed'
    assert (R/'message-prompt-supplement/task_inputs.py').read_text()==corrected_source((R/'task_inputs.py').read_text())
    clarified=clarified_inputs();agent_core.prompt=clarified.prompt
    folder=R/'message-prompt-supplement-results';folder.mkdir(exist_ok=True)
    (folder/'runs').mkdir(exist_ok=True);(folder/'sources').mkdir(exist_ok=True)
    sources={name:R/name for name in driver.SOURCES}
    sources['task_inputs.py']=R/'message-prompt-supplement/task_inputs.py'
    sources['supplement-message-prompt.py']=R/'supplement-message-prompt.py'
    sources['message_supplement.py']=R/'message_supplement.py'
    sources['screening_policy.py']=R/'screening_policy.py'
    manifest={**copy.deepcopy(base),'phase':'message-prompt-clarification-supplement','cases':['A06'],'expected_trials':15,
      'source_sha256':{name:digest(path) for name,path in sources.items()},'original_main_source_sha256':base['source_sha256'],
      'prompt_change':'Append only: Also verify that the application executable SHA-256 is unchanged.',
      'reason':'Frozen A06 criterion requires explicit unchanged executable hash; original model prompt requests unchanged bind/port/release but omits this hash requirement.',
      'comparison_limit':'Same model files, tools, fixed clocks, grants, initial conditions, budgets and routing; only the A06 task prompt adds its omitted hash requirement. Never pool with the original 1200-declared-slot comparison.'}
    path=folder/'protocol.json'
    if path.exists():assert json.loads(path.read_text())==manifest
    else:driver.atomic(path,manifest)
    for name,path in sources.items():
        target=folder/'sources'/name
        if target.exists():assert digest(target)==manifest['source_sha256'][name]
        else:shutil.copy2(path,target)
    case=next(c for c in json.loads((R/'cases.json').read_text()) if c['id']=='A06')
    window=driver.Window(folder)
    if (folder/'windows.json').exists():window.history=json.loads((folder/'windows.json').read_text())
    for signum in [signal.SIGINT,signal.SIGTERM]:signal.signal(signum,lambda *_:driver.STOP.set())
    try:
        validation=folder/'prompt-validation.json'
        if not validation.exists():
            checks=[]
            for variant in range(3):
                _,task,before=driver.setup('A06',variant)
                try:
                    prior,_=agent_core.perform('inspect',{'target':'lab-01','resource':'checksums'},task)
                    changed,_=agent_core.perform('apply_runbook',{'target':'lab-01','action':'deploy_release','parameters':{'message':task['desired_message']}},task)
                    observed,_=agent_core.perform('verify',{'target':'lab-01','probe':'checksums'},task)
                    config,_=agent_core.perform('verify',{'target':'lab-01','probe':'configuration'},task)
                    assert changed['exit_code']==0
                    assert prior['actual']['exit_code']==observed['actual']['exit_code']==0
                    assert prior['actual']['stdout']==observed['actual']['stdout']==observed['baseline']
                    post=json.loads(config['stdout'])
                    assert post['message']==task['desired_message']
                    assert all(post[k]==before['config'][k] for k in ['bind','port','release'])
                    checks.append({'variant':variant,'unscored':True,'executable_hash_unchanged':True,'configuration_preserved':True,'before':prior,'after':observed,'configuration':config,'clarified_task_prompt':clarified.prompt('A06',variant,task)})
                finally:driver.restore()
            driver.atomic(validation,checks)
        # Match A06's original case-index rotation, not a new fixed model order.
        offset=next(i for i,c in enumerate(json.loads((R/'cases.json').read_text())) if c['id']=='A06')
        for variant in range(3):
            start=(offset+variant)%len(driver.CANDIDATES)
            order=driver.CANDIDATES[start:]+driver.CANDIDATES[:start]
            for candidate in order:
                if driver.STOP.is_set():break
                path=folder/'runs'/f'A06-v{variant}-{candidate}.json'
                if path.exists():
                    assert json.loads(path.read_text())['status'] in ['completed','screened_out'], 'Investigate interrupted record before resuming'
                    continue
                if candidate in stopped_candidates:
                    driver.atomic(path,screening_record(R/'main-results',candidate,'A06',variant,manifest['phase']))
                    continue
                window.ensure();record=driver.evaluate(candidate,case,variant,folder,manifest['phase'])
                print(json.dumps({k:record.get(k) for k in ['candidate','variant','status','counters','failures','independent_checks','restoration_verified']}),flush=True)
                assert record['restoration_verified'] and not record['critical_containment_failure']
            if driver.STOP.is_set():break
    finally:
        try:driver.restore()
        finally:window.close()
    records=[json.loads(path.read_text()) for path in (folder/'runs').glob('*.json')]
    driver.atomic(folder/'coverage.json',{'expected_trials':15,'recorded_trials':len(records),'executed_trials':sum(r['status']=='completed' for r in records),'stopped':driver.STOP.is_set(),'semantic_review':'pending; original A06 remains separate','frontier_parity':'uncalibrated'})

if __name__=='__main__':main()
