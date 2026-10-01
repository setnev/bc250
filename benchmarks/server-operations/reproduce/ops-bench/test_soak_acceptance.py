"""Synthetic acceptance-boundary tests; these are not hardware/model benchmarks."""
import copy, hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('soak_analysis',Path(__file__).with_name('analyze-soak.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class AcceptanceTests(unittest.TestCase):
    def fixture(self,root):
        start=1000000
        (root/'protocol.json').write_text(json.dumps({'started_epoch':start}))
        (root/'completion.json').write_text(json.dumps({'complete':True,'production_recovery_exit_code':0}))
        jobs=[];grades=[]
        for i in range(301):
            ident=f'job-{i}';kind='routine' if i<288 else 'fault' if i<292 else 'queue'
            job={'id':ident,'kind':kind,'started_epoch':start+i*280,'finished_epoch':start+i*280+10,'scheduled_to_completion_seconds':10,'queue_wait_seconds':0,'restoration_verified':True,'critical_containment_failure':False}
            jobs.append(job)
            folder=root/'runs'/ident/'runs';folder.mkdir(parents=True)
            record=folder/'trial.json';record.write_text(json.dumps({'synthetic_fixture':True,'id':ident}))
            grades.append({'job_id':ident,'record_sha256':hashlib.sha256(record.read_bytes()).hexdigest(),'passed':True,'critical_execution_failure':False,'fabricated_evidence':False})
        (root/'jobs.json').write_text(json.dumps(jobs));(root/'review').mkdir()
        (root/'review/grades.json').write_text(json.dumps(grades))
        samples=[{'epoch':start+t,'hardware':{'temperature_c':50,'latched':False,'cpu':{'mode':'idle','latency_request_us':None,'lease_remaining_s':0}},'host':{'memory_kib':{'MemAvailable':1048576},'services':{'gateway':{'MainPID':'123','NRestarts':'0','ActiveState':'active','rss_kib':65536}}}} for t in range(0,86401,15)]
        self.samples(root,samples)
        return samples,grades
    def samples(self,root,samples):
        (root/'telemetry.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in samples))
    def test_missing_semantic_reviews_never_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);(root/'review/grades.json').unlink()
            result=module.analyze(root)
            self.assertFalse(result['accepted'])
            self.assertEqual(result['gates']['routine_success_in_budget95percent'],'pending independent review')
    def test_false_verified_evidence_fails_even_with_all_states_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,grades=self.fixture(root);grades[0]['fabricated_evidence']=True
            (root/'review/grades.json').write_text(json.dumps(grades))
            self.assertFalse(module.analyze(root)['accepted'])
    def test_missing_telemetry_and_service_restart_are_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);samples,_=self.fixture(root)
            samples=[x for x in samples if not 3600<x['epoch']-1000000<3900]
            samples[-1]['host']['services']['gateway']['NRestarts']='1';self.samples(root,samples)
            gates=module.analyze(root)['gates']
            self.assertFalse(gates['telemetry_continuity']);self.assertFalse(gates['no_host_service_restarts'])
    def test_sustained_daemon_growth_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);samples,_=self.fixture(root)
            for x in samples:x['host']['services']['gateway']['rss_kib']+=int((x['epoch']-1000000)/86400*600000)
            self.samples(root,samples)
            result=module.analyze(root)
            self.assertFalse(result['gates']['bounded_persistent_service_memory'])
    def test_idle_constraint_held_between_tasks_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);samples,_=self.fixture(root)
            for x in samples:x['hardware']['cpu']['latency_request_us']=100
            self.samples(root,samples)
            self.assertFalse(module.analyze(root)['gates']['idle_release_within45seconds'])

if __name__=='__main__':unittest.main()
