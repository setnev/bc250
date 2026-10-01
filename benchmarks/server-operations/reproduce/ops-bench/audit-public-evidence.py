"""Audit actual complete export against private evidence before public upload.

This checks data fidelity and archive integrity, not model quality or manual
privacy acceptance. Run only after export; private rules never enter output.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, runpy, tarfile
from publication_privacy import Scrubber, sanitize_record

ROOT=Path(__file__).resolve().parent
PHASES=('main-results','latency-results','restore-file-supplement-results',
        'message-prompt-supplement-results','soak-smoke-results','soak-results')

def read(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def audit(root,public,rules,archive):
    # Actual coverage, original source pins, SHA reviews and preflight gates.
    exporter=runpy.run_path(str(root/'export-public-results.py'))
    exporter['validate'](root)
    scrubber=Scrubber(read(rules))
    manifest=read(public/'evidence-manifest.json')
    assert manifest['frontier_parity']=='uncalibrated'
    assert manifest['owner_workload_coverage']=='unmeasured'
    entries={e['path']:e for e in manifest['files']}
    assert len(entries)==len(manifest['files']),'Duplicate manifest member'
    actual={str(p.relative_to(public)) for p in public.rglob('*') if p.is_file()}
    assert actual==set(entries)|{'evidence-manifest.json'},'Unmanifested/missing export files'
    for name,entry in entries.items():
        path=public/name
        assert not path.is_symlink() and not Path(name).is_absolute() and '..' not in Path(name).parts
        assert path.stat().st_size==entry['bytes'] and digest(path)==entry['public_sha256']
        scrubber.check(path.read_text())
        original=root/name
        if 'as_tested_original_sha256' in entry:
            assert original.is_file() and digest(original)==entry['as_tested_original_sha256']

    stop_hashes={digest(p):digest(public/'main-results/runs'/p.name)
                 for p in (root/'main-results/runs').glob('*.json')}
    transcript_count=0;review_count=0
    for phase in PHASES:
        private_folder=root/phase;public_folder=public/phase
        if phase=='latency-results':
            assert read(public_folder/'trials.json')==scrubber.value(read(private_folder/'trials.json'))
            continue
        private_grades=read(private_folder/'review/grades.json')
        public_grades=read(public_folder/'review/grades.json')
        assert len(private_grades)==len(public_grades)
        nested=phase in ('soak-smoke-results','soak-results')
        for old,new in zip(private_grades,public_grades):
            if nested:
                paths=list((private_folder/'runs'/old['job_id']/'runs').glob('*.json'))
                assert len(paths)==1
                private_path=paths[0]
            else:
                private_path=private_folder/'runs'/f"{old['case_id']}-v{old['variant']}-{old['candidate']}.json"
            public_path=public_folder/private_path.relative_to(private_folder)
            expected=sanitize_record(read(private_path),digest(private_path),scrubber)
            if expected.get('main_critical_stop'):
                stop=expected['main_critical_stop'];original=stop['record_sha256']
                stop['as_tested_original_record_sha256']=original
                stop['record_sha256']=stop_hashes[original]
            assert read(public_path)==expected,'Transformed transcript differs from declared scrub'
            assert new==exporter['bind_grade'](old,digest(private_path),digest(public_path),scrubber)
            transcript_count+=1;review_count+=1
    assert transcript_count==review_count==1533

    # Rationale corrections are a separate trail, never replacements for grades.
    original_amendments=exporter['validate_rationale_amendments'](root,read(root/'soak-results/review/grades.json'))
    expected_amendments=None
    if original_amendments is not None:
        expected_amendments=exporter['bind_rationale_amendments'](
            original_amendments,read(root/'soak-results/review/grades.json'),
            read(public/'soak-results/review/grades.json'),scrubber)
        assert read(public/'soak-results/review/rationale-amendments.json')==expected_amendments
        public_grades={g['job_id']:g for g in read(public/'soak-results/review/grades.json')}
        for a in expected_amendments['amendments']:
            grade=public_grades[a['job_id']]
            assert a['record_sha256']==grade['record_sha256']
            assert a['original_grade_canonical_sha256']==exporter['canonical_grade_sha'](grade)
            assert a['original_rationale']==grade['rationale']
    else:
        assert not (public/'soak-results/review/rationale-amendments.json').exists()
    post_timing_verified=[]
    for name in exporter['POST_TIMING_FILES']:
        if (root/name).exists():
            assert read(public/name)==scrubber.value(read(root/name))
            post_timing_verified.append(name)

    # Aggregate values must survive transformation; public SHA-bound catalogs
    # were recomputed by the exporter, not copied from private grades.
    unchanged=['main-results/catalog/reviewed-candidates.json',
               'main-results/catalog/variant-quality.json',
               'main-results/catalog/inference-performance.json',
               'main-results/catalog/failure-label-counts.json',
               'restore-file-supplement-results/catalog/comparison.json',
               'message-prompt-supplement-results/catalog/comparison.json',
               'latency-results/tool-latency-summary.json','soak-results/acceptance.json']
    for name in unchanged:
        assert read(public/name)==scrubber.value(read(root/name)),'Aggregate changed during export: '+name
    common=read(public/'main-results/catalog/common-executed-cohort.json')
    original=read(root/'main-results/catalog/common-executed-cohort.json')
    assert common['full_review_sha256']==digest(public/'main-results/review/grades.json')
    assert {k:v for k,v in common.items() if k!='full_review_sha256'}=={k:v for k,v in original.items() if k!='full_review_sha256'}

    assert archive.stat().st_size<95*1024**2
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers()
        assert {m.name for m in members}==actual and len(members)==len(actual)
        for member in members:
            assert member.isfile() and (member.uid,member.gid,member.uname,member.gname,member.mtime,member.mode)==(0,0,'','',0,0o644)
            with tar.extractfile(member) as stream:archived=hashlib.sha256(stream.read()).hexdigest()
            assert archived==digest(public/member.name),'Archive data differs from export'
    return {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'complete_original_coverage_and_provenance_verified':True,
            'public_manifest_members_verified':len(entries),
            'declared_records_and_sha_bound_grades_verified':transcript_count,
            'latency_requests_verified':120,'aggregate_fidelity_verified':True,
            'rationale_only_amendments_verified':len(expected_amendments['amendments']) if expected_amendments else 0,
            'post_timing_inventory_artifacts_verified':post_timing_verified,
            'archive_bytes':archive.stat().st_size,'archive_sha256':digest(archive),
            'archive_member_identity_and_data_verified':True,
            'privacy_scope':'Known-private-value scan and exact declared transforms verified; separate manual review still required',
            'frontier_parity':'uncalibrated','owner_workload_coverage':'unmeasured'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--public',type=Path,required=True);p.add_argument('--private-rules',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    args=p.parse_args();result=audit(args.root,args.public,args.private_rules,args.archive)
    args.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
