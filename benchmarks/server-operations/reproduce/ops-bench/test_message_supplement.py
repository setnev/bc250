"""Synthetic provenance checks, never actual model or VM benchmark results."""
from pathlib import Path
import json, runpy, tempfile, unittest
from message_supplement import CLARIFICATION, ORIGINAL_PROMPT, corrected_source, sha, validate

R=Path(__file__).resolve().parent
def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

def fixture(root):
    main=root/'main-results';(main/'sources').mkdir(parents=True,exist_ok=True)
    protocol_path=main/'protocol.json'
    if protocol_path.exists():base=json.loads(protocol_path.read_text())
    else:
        (main/'sources/dummy.py').write_text('# Synthetic frozen source\n')
        base={'candidates':['model-'+str(i) for i in range(5)],'cases':['A06'],'variants':[0,1,2],
              'expected_trials':15,'source_sha256':{'dummy.py':sha(main/'sources/dummy.py')}}
    (main/'sources/task_inputs.py').write_bytes((R/'task_inputs.py').read_bytes())
    base['source_sha256']['task_inputs.py']=sha(main/'sources/task_inputs.py');write(protocol_path,base)
    folder=root/'message-prompt-supplement-results';(folder/'sources').mkdir(parents=True)
    for name in base['source_sha256']:(folder/'sources'/name).write_bytes((main/'sources'/name).read_bytes())
    (folder/'sources/task_inputs.py').write_text(corrected_source((main/'sources/task_inputs.py').read_text()))
    for name in ['supplement-message-prompt.py','message_supplement.py','screening_policy.py']:(folder/'sources'/name).write_bytes((R/name).read_bytes())
    write(folder/'protocol.json',{'phase':'message-prompt-clarification-supplement','cases':['A06'],'expected_trials':15,
         'candidates':base['candidates'],'original_main_source_sha256':base['source_sha256'],
         'source_sha256':{p.name:sha(p) for p in (folder/'sources').iterdir()}})
    write(folder/'coverage.json',{'recorded_trials':15,'stopped':False})
    observed={'actual':{'exit_code':0,'stdout':'a'*64+'  /opt/ops-lab/service.py\n'},'baseline':'a'*64+'  /opt/ops-lab/service.py\n'}
    write(folder/'prompt-validation.json',[{'variant':v,'unscored':True,'executable_hash_unchanged':True,
         'configuration_preserved':True,'before':observed,'after':observed,
         'clarified_task_prompt':ORIGINAL_PROMPT+CLARIFICATION} for v in range(3)])
    grades=[]
    for candidate in base['candidates']:
        for variant in range(3):
            path=folder/'runs'/f'A06-v{variant}-{candidate}.json'
            write(path,{'candidate':candidate,'case_id':'A06','variant':variant,'status':'completed','restoration_verified':True})
            grades.append({'candidate':candidate,'case_id':'A06','variant':variant,'record_sha256':sha(path),'passed':False})
    write(folder/'review/grades.json',grades)
    return folder

class MessageSupplementTests(unittest.TestCase):
    def test_only_a06_prompt_changes_without_expanding_authority(self):
        original=runpy.run_path(str(R/'task_inputs.py'))
        corrected=runpy.run_path(str(R/'message-prompt-supplement/task_inputs.py'))
        self.assertEqual(original['COMMON'],corrected['COMMON'])
        for case in original['TASKS']:
            for variant in range(3):
                context={'allowed_runbooks':['deploy_release'],'desired_message':'SYNTHETIC_OK'}
                before=original['prompt'](case,variant,context);after=corrected['prompt'](case,variant,context)
                self.assertEqual(after,before.replace(ORIGINAL_PROMPT,ORIGINAL_PROMPT+CLARIFICATION) if case=='A06' else before)
        self.assertEqual((R/'message-prompt-supplement/task_inputs.py').read_text(),corrected_source((R/'task_inputs.py').read_text()))

    def test_failed_model_quality_publishable_but_missing_or_stale_review_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=fixture(root);self.assertEqual(validate(root)['trials'],15)
            record=next((folder/'runs').glob('*.json'));record.write_text(record.read_text()+'\n')
            with self.assertRaises(AssertionError):validate(root)
            record.write_text(record.read_text().rstrip())
            grade_path=folder/'review/grades.json';grades=json.loads(grade_path.read_text());write(grade_path,grades[:-1])
            with self.assertRaises(AssertionError):validate(root)

    def test_hidden_other_source_change_or_false_validation_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=fixture(root)
            checks=folder/'prompt-validation.json';rows=json.loads(checks.read_text());rows[0]['after']['actual']['stdout']='changed hash'
            write(checks,rows)
            with self.assertRaises(AssertionError):validate(root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=fixture(root);source=folder/'sources/dummy.py';source.write_text('# Hidden source modification\n')
            p=folder/'protocol.json';protocol=json.loads(p.read_text());protocol['source_sha256']['dummy.py']=sha(source);write(p,protocol)
            with self.assertRaises(AssertionError):validate(root)

if __name__=='__main__':unittest.main()
