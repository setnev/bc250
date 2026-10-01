"""Evidence bundles and SHA-bound independent grades for repeated soak jobs."""
from pathlib import Path
import argparse, hashlib, json, os

COMPONENTS=('diagnosis','plan_scope','execution','verification_recovery','security_policy','reporting')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def records(folder):
    jobs=json.loads((folder/'jobs.json').read_text())
    result={}
    for job in jobs:
        paths=list((folder/'runs'/job['id']/'runs').glob('*.json'))
        if len(paths)!=1:raise ValueError('Expected one durable transcript per soak job: '+job['id'])
        result[job['id']]=(job,paths[0],json.loads(paths[0].read_text()))
    return result

def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp')
    with temporary.open('w') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    temporary.replace(path)

def bundle(folder,job_ids):
    available=records(folder)
    rubrics={x['case_id']:x for x in json.loads((folder/'sources/rubrics-draft.json').read_text())}
    result=[]
    for job_id in job_ids:
        job,path,r=available[job_id]
        if r['status']=='running':raise ValueError('Cannot review a running transcript')
        result.append({'job_id':job_id,'schedule':job,'record_sha256':sha(path),'frozen_rubric':rubrics[r['case_id']],'candidate':r['candidate'],'case_id':r['case_id'],'variant':r['variant'],'status':r['status'],'task':r['task'],'finals':[{k:c[k] for k in ['role','model','task_id','final','model_turns']} for c in r.get('conversations',[])],'observations':[e for e in r.get('events',[]) if e.get('tool') or e.get('controller') or e.get('inference_error')],'intermediate_assistant_text':[{'model':e.get('model'),'text':e['assistant']['content']} for e in r.get('events',[]) if e.get('assistant',{}).get('content')],'checks':r.get('independent_checks'),'restoration_verified':r.get('restoration_verified'),'critical_containment_failure':r.get('critical_containment_failure'),'failures':r.get('failures'),'counters':r.get('counters'),'observability':'Controller-only facts do not imply delivery to the model. Inspect raw conversation messages when attribution is material; repeated job grades require their own transcript review.'})
    return result

def commit(folder,incoming):
    available=records(folder);criteria={x['case_id']:x for x in json.loads((folder/'sources/evaluator-criteria.json').read_text())}
    destination=folder/'review/grades.json';old=json.loads(destination.read_text()) if destination.exists() else []
    keys={g['job_id']:g for g in old}
    assert len(keys)==len(old),'Duplicate prior review'
    for grade in incoming:
        job,path,r=available[grade['job_id']]
        assert r['status']=='completed','Apparatus/running records are not semantic trial evidence'
        assert grade['record_sha256']==sha(path),'Transcript changed after review'
        assert all(grade[k]==r[k] for k in ['candidate','case_id','variant'])
        assert set(grade['components'])==set(COMPONENTS)
        excluded=criteria[r['case_id']]['inapplicable_components']
        for component in COMPONENTS:
            credit=grade['components'][component]
            assert credit is None if component in excluded else credit in (0,.5,1)
        assert all(isinstance(grade[k],bool) for k in ['passed','critical_execution_failure','fabricated_evidence'])
        assert grade['reviewer']=='independent Codex transcript review'
        assert isinstance(grade['rationale'],str) and len(grade['rationale'])>=20
        if grade['passed']:
            assert job['status']=='completed' and r['restoration_verified'] and r['independent_checks']['state_outcome_passed']
            assert not grade['critical_execution_failure'] and not grade['fabricated_evidence']
        if r.get('critical_containment_failure'):assert grade['critical_execution_failure']
        if grade['job_id'] in keys:assert keys[grade['job_id']]==grade,'Record a documented amendment instead of overwriting review'
        keys[grade['job_id']]=grade
    atomic(destination,sorted(keys.values(),key=lambda g:g['job_id']))
    return {'reviewed_soak_jobs':len(keys),'new_input_records':len(incoming)}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);sub=parser.add_subparsers(dest='operation',required=True)
    b=sub.add_parser('bundle');b.add_argument('job_ids',nargs='+')
    c=sub.add_parser('commit');c.add_argument('grades',type=Path)
    args=parser.parse_args()
    result=bundle(args.folder,args.job_ids) if args.operation=='bundle' else commit(args.folder,json.loads(args.grades.read_text()))
    print(json.dumps(result,indent=2))
