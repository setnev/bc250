"""Publication integrity: rewritten reviews and archives must remain verifiable."""
import copy, hashlib, json, runpy, tarfile, tempfile, unittest
from pathlib import Path
from publication_privacy import Scrubber, json_bytes
from test_soak_preflight import smoke_fixture
from soak_preflight import validate_smoke
from test_message_supplement import fixture as message_fixture
from screening_policy import STOP_REASON, screening_record, validate_screening_record
from test_screening_policy import fixture as screening_fixture

EXPORT=runpy.run_path(str(Path(__file__).with_name('export-public-results.py')))

class ExportTests(unittest.TestCase):
    def amendment_fixture(self,root):
        grades=[];amendments=[]
        for job in sorted(EXPORT['RATIONALE_AMENDMENT_JOBS']):
            path=root/'soak-results/runs'/job/'runs/transcript.json';path.parent.mkdir(parents=True)
            path.write_bytes(json_bytes({'conversations':[{'final':'Observed evidence stays unresolved.'}]}))
            grade={'job_id':job,'record_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                   'rationale':'private-operator overstates health and length.',
                   'components':{'reporting':.5},'passed':True,'critical_execution_failure':False,'fabricated_evidence':False}
            grades.append(grade)
            amendments.append({'job_id':job,'record_sha256':grade['record_sha256'],
                               'original_grade_canonical_sha256':EXPORT['canonical_grade_sha'](grade),
                               'original_rationale':grade['rationale'],'corrected_rationale':'private-operator overstates health.',
                               'final_whitespace_word_count':4,'maximum_words':120,'components_unchanged':True,
                               'pass_and_failure_flags_unchanged':True,'human_semantic_adjudication_replaced':False})
        path=root/'soak-results/review/rationale-amendments.json';path.parent.mkdir()
        path.write_bytes(json_bytes({'amendments':amendments}))
        return grades,path

    def test_amendments_rebind_both_hashes_without_replacing_original_grade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grades,path=self.amendment_fixture(root);before=copy.deepcopy(grades)
            source=EXPORT['validate_rationale_amendments'](root,grades)
            scrubber=Scrubber({'replacements':{'private-operator':'test-operator'}})
            public=[EXPORT['bind_grade'](g,g['record_sha256'],str(i)*64,scrubber) for i,g in enumerate(grades)]
            preserved=copy.deepcopy(public)
            clean=EXPORT['bind_rationale_amendments'](source,grades,public,scrubber)
            for old,new,grade in zip(source['amendments'],clean['amendments'],public):
                self.assertEqual(new['record_sha256'],grade['record_sha256'])
                self.assertEqual(new['as_tested_original_record_sha256'],old['record_sha256'])
                self.assertEqual(new['original_grade_canonical_sha256'],EXPORT['canonical_grade_sha'](grade))
                self.assertEqual(new['as_tested_original_grade_canonical_sha256'],old['original_grade_canonical_sha256'])
                self.assertEqual(new['original_rationale'],grade['rationale'])
                self.assertNotIn('private-operator',new['corrected_rationale'])
            self.assertEqual(grades,before);self.assertEqual(public,preserved)

    def test_amendment_rejects_stale_grade_false_wordcount_and_unknown_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grades,path=self.amendment_fixture(root);original=json.loads(path.read_text())
            for field,value in [('original_grade_canonical_sha256','0'*64),
                                ('final_whitespace_word_count',121),('job_id','unreviewed-job')]:
                changed=copy.deepcopy(original);changed['amendments'][0][field]=value
                path.write_bytes(json_bytes(changed))
                with self.subTest(field=field),self.assertRaises(AssertionError):
                    EXPORT['validate_rationale_amendments'](root,grades)

    def complete_fixture(self,root):
        """Synthetic coverage only; never model results or operational evidence."""
        candidates=['qwen3.5-0.8b','qwen3.5-2b','qwen3.5-4b','qwen3.5-9b','worker2b-planner9b']
        cases=[f'T{i:02}' for i in range(80)]
        source=root/'dummy.py';source.write_text('# Synthetic source fixture\n')
        source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
        for phase in ['main-results','latency-results','soak-results']:
            folder=root/phase;folder.mkdir();(folder/'sources').mkdir()
            (folder/'sources/dummy.py').write_bytes(source.read_bytes())
        main=root/'main-results';(main/'runs').mkdir();(main/'review').mkdir()
        (main/'protocol.json').write_bytes(json_bytes({'candidates':candidates,'cases':cases,'variants':[0,1,2],
          'expected_trials':1200,'source_sha256':{'dummy.py':source_sha}}))
        grades=[]
        for candidate in candidates:
            for case in cases:
                for variant in range(3):
                    record={'candidate':candidate,'case_id':case,'variant':variant,'status':'completed','restoration_verified':True}
                    path=main/'runs'/f'{case}-v{variant}-{candidate}.json';path.write_bytes(json_bytes(record))
                    grades.append({**{k:record[k] for k in ['candidate','case_id','variant']},'record_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        (main/'review/grades.json').write_bytes(json_bytes(grades))
        latency=root/'latency-results'
        latency_rows=[{'model':model,'condition':condition,'trial':i} for model in candidates[:-1]
                      for condition,count in [('warm',20),('fresh_load',10)] for i in range(count)]
        (latency/'trials.json').write_bytes(json_bytes(latency_rows));(latency/'summary.json').write_bytes(json_bytes([]))
        (latency/'protocol.json').write_bytes(json_bytes({'source_sha256':{'dummy.py':source_sha}}))
        soak=root/'soak-results';(soak/'review').mkdir()
        (soak/'protocol.json').write_bytes(json_bytes({'source_sha256':{'dummy.py':source_sha}}))
        (soak/'completion.json').write_bytes(json_bytes({'complete':True,'elapsed_seconds':86400}))
        jobs=[{'id':f'test-{i}','kind':'routine' if i<288 else 'fault' if i<292 else 'queue'} for i in range(301)]
        (soak/'jobs.json').write_bytes(json_bytes(jobs));soak_grades=[]
        for job in jobs:
            path=soak/'runs'/job['id']/'runs/transcript.json';path.parent.mkdir(parents=True)
            path.write_bytes(json_bytes({'test':job['id']}))
            soak_grades.append({'job_id':job['id'],'record_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        (soak/'review/grades.json').write_bytes(json_bytes(soak_grades))
        (soak/'acceptance.json').write_bytes(json_bytes({'accepted':False,'test_fixture':True}))
        supplement=root/'restore-file-supplement-results';supplement.mkdir()
        (supplement/'sources').mkdir();(supplement/'sources/dummy.py').write_bytes(source.read_bytes())
        (supplement/'protocol.json').write_bytes(json_bytes({'phase':'restore-file-interface-supplement','cases':['B04'],
            'expected_trials':15,'candidates':candidates,'source_sha256':{'dummy.py':source_sha}}))
        (supplement/'coverage.json').write_bytes(json_bytes({'recorded_trials':15,'stopped':False}))
        (supplement/'interface-validation.json').write_bytes(json_bytes([
            {'variant':i,'unscored':True,'wrong_target_rejected':True,'extra_path_rejected':True} for i in range(3)]))
        (supplement/'runs').mkdir();(supplement/'review').mkdir();supplement_grades=[]
        for candidate in candidates:
            for variant in range(3):
                path=supplement/'runs'/f'B04-v{variant}-{candidate}.json'
                path.write_bytes(json_bytes({'status':'completed','restoration_verified':True}))
                supplement_grades.append({'candidate':candidate,'case_id':'B04','variant':variant,
                    'record_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        (supplement/'review/grades.json').write_bytes(json_bytes(supplement_grades))
        selection_path,selection=smoke_fixture(root)
        smoke=validate_smoke(root,selection_path,selection)
        (soak/'protocol.json').write_bytes(json_bytes({'source_sha256':{'dummy.py':source_sha},'production_gateway_smoke':smoke}))
        message_fixture(root)

    def test_grade_binds_public_digest_and_retains_original(self):
        grade={'record_sha256':'a'*64,'passed':False,'fabricated_evidence':True,
               'rationale':'private-operator claimed an unperformed command.'}
        clean=EXPORT['bind_grade'](grade,'a'*64,'b'*64,Scrubber({'replacements':{'private-operator':'test-operator'}}))
        self.assertEqual(clean['record_sha256'],'b'*64)
        self.assertEqual(clean['as_tested_original_record_sha256'],'a'*64)
        self.assertFalse(clean['passed']);self.assertTrue(clean['fabricated_evidence'])
        self.assertNotIn('private-operator',clean['rationale'])
        self.assertEqual(grade['record_sha256'],'a'*64)

    def test_stale_grade_rejected(self):
        with self.assertRaisesRegex(ValueError,'stale'):
            EXPORT['bind_grade']({'record_sha256':'c'*64},'a'*64,'b'*64,Scrubber({}))

    def test_archive_deterministic_without_filesystem_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';data.mkdir();(data/'sample.json').write_bytes(json_bytes({'test':1}))
            a=root/'a.tar.gz';b=root/'b.tar.gz'
            self.assertEqual(EXPORT['archive'](data,a),EXPORT['archive'](data,b))
            with tarfile.open(a) as tar:
                member=tar.getmembers()[0]
                self.assertEqual((member.name,member.uid,member.gid,member.uname,member.gname,member.mtime),('sample.json',0,0,'','',0))
                self.assertEqual(tar.extractfile(member).read(),(data/'sample.json').read_bytes())

    def test_record_written_with_sanitized_hash_and_original_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);original=root/'private.json'
            original.write_bytes(json_bytes({'final':'private-operator Bearer [REDACTED]','seconds':1.23}))
            output=root/'output';output.mkdir()
            writer=EXPORT['Exporter'](output,Scrubber({'replacements':{'private-operator':'test-operator'},'secrets':['fake-private-key']}))
            public_sha=writer.record(original,Path('main-results/runs/test.json'))
            path=output/'main-results/runs/test.json';clean=json.loads(path.read_text())
            self.assertEqual(public_sha,hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(clean['seconds'],1.23)
            self.assertEqual(clean['publication_provenance']['as_tested_original_record_sha256'],hashlib.sha256(original.read_bytes()).hexdigest())
            self.assertNotIn('fake-private-key',path.read_text())

    def test_incomplete_phase_refuses_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'main-results').mkdir()
            (root/'main-results/protocol.json').write_text(json.dumps({'candidates':['test'],'cases':['N01'],'variants':[0],'expected_trials':1}))
            destination=root/'output'
            with self.assertRaises(AssertionError):EXPORT['export'](root,destination,{})
            self.assertFalse(destination.exists())

    def test_screened_reference_rebinds_public_critical_record_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);main=screening_fixture(root);path=main/'runs/G01-v0-stopped.json'
            record=json.loads(path.read_text());record['final']='private-operator';path.write_bytes(json_bytes(record))
            original_sha=hashlib.sha256(path.read_bytes()).hexdigest()
            output=root/'public';output.mkdir()
            writer=EXPORT['Exporter'](output,Scrubber({'replacements':{'private-operator':'test-operator'}}))
            writer.json(main/'protocol.json',Path('main-results/protocol.json'))
            public_sha=writer.record(path,Path('main-results/runs')/path.name)
            self.assertNotEqual(public_sha,original_sha)
            path=root/'annex.json';path.write_bytes(json_bytes(screening_record(main,'stopped','B04',0,'supplement')))
            writer.record(path,Path('supplement/runs/annex.json'),{original_sha:public_sha})
            clean=json.loads((output/'supplement/runs/annex.json').read_text())
            self.assertEqual(clean['main_critical_stop']['record_sha256'],public_sha)
            self.assertEqual(clean['main_critical_stop']['as_tested_original_record_sha256'],original_sha)
            validate_screening_record(clean,output/'main-results')

    def test_coverage_gate_and_failed_quality_result_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.complete_fixture(root)
            records,grades,jobs,soak_grades=EXPORT['validate'](root)
            self.assertEqual((len(records),len(grades),len(jobs),len(soak_grades)),(1200,1200,301,301))
            # A failed quality result is eligible for honest reporting, but
            # missing measured coverage or less than 24 hours is not complete.
            completion=root/'soak-results/completion.json'
            completion.write_bytes(json_bytes({'complete':True,'elapsed_seconds':86399}))
            with self.assertRaises(AssertionError):EXPORT['validate'](root)
            completion.write_bytes(json_bytes({'complete':True,'elapsed_seconds':86400}))
            rows=root/'latency-results/trials.json';original=json.loads(rows.read_text())
            rows.write_bytes(json_bytes(original[:-1]+[original[0]]))
            with self.assertRaises(AssertionError):EXPORT['validate'](root)
            rows.write_bytes(json_bytes(original))
            next(iter(records.values())).unlink()
            with self.assertRaises(AssertionError):EXPORT['validate'](root)

    def test_approved_critical_stop_is_publishable_without_resuming_or_inventing_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.complete_fixture(root);main=root/'main-results'
            grade_path=main/'review/grades.json';grades=json.loads(grade_path.read_text())
            for grade in grades:
                if grade['candidate']!='qwen3.5-4b':continue
                path=main/'runs'/f"{grade['case_id']}-v{grade['variant']}-{grade['candidate']}.json"
                critical=grade['case_id']=='T00' and grade['variant']==0
                if critical:
                    record=json.loads(path.read_text());record.update(critical_containment_failure=True,
                        synthetic_secret_disclosed=True,independent_checks={'protected_state_preserved':True})
                else:record={'candidate':grade['candidate'],'case_id':grade['case_id'],'variant':grade['variant'],
                            'status':'screened_out','reason':STOP_REASON}
                path.write_bytes(json_bytes(record));grade.update(record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    passed=False,critical_execution_failure=critical,components={'execution':None,'security_policy':0})
                if not critical:grade['review_status']='unexecuted_screening_record'
            grade_path.write_bytes(json_bytes(grades))
            for phase,case in [('restore-file-supplement-results','B04'),('message-prompt-supplement-results','A06')]:
                grade_path=root/phase/'review/grades.json';grades=json.loads(grade_path.read_text())
                for grade in grades:
                    if grade['candidate']!='qwen3.5-4b':continue
                    path=root/phase/'runs'/f"{case}-v{grade['variant']}-{grade['candidate']}.json"
                    path.write_bytes(json_bytes(screening_record(main,grade['candidate'],case,grade['variant'],phase)))
                    grade.update(record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),passed=False,
                        review_status='unexecuted_screening_record',components={'execution':None,'security_policy':0})
                grade_path.write_bytes(json_bytes(grades))
            records,grades,_,_=EXPORT['validate'](root)
            self.assertEqual(len(records),1200)
            self.assertEqual(sum(json.loads(p.read_text())['status']=='completed' for p in records.values()),961)
            self.assertEqual(sum(g.get('review_status')=='unexecuted_screening_record' for g in grades),239)
            # A correction annex may not quietly run the stopped model again.
            path=root/'message-prompt-supplement-results/runs/A06-v0-qwen3.5-4b.json'
            path.write_bytes(json_bytes({'status':'completed','restoration_verified':True}))
            with self.assertRaisesRegex(AssertionError,'resumed'):EXPORT['validate'](root)

if __name__=='__main__':unittest.main()
