"""Export an explicit evidence allowlist; never upload private working trees.

Requires completed comparison, latency phase and full-duration soak with all
independent reviews. A failed semantic acceptance gate remains publishable as a
failed result. Private privacy rules are supplied separately and never copied.
"""
from pathlib import Path
import argparse, collections, gzip, hashlib, json, runpy, tarfile
from publication_privacy import Scrubber, json_bytes, sanitize_record
from soak_preflight import validate_smoke
from message_supplement import validate as validate_message_supplement
from screening_policy import validate_main, validate_screening_record, critical_stops

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())

RATIONALE_AMENDMENT_JOBS={'queue-64800-0','routine-020','routine-216','routine-234'}
POST_TIMING_FILES=('post-timing-runtime-validation.json','post-timing-model-catalog-validation.json',
                  'post-timing-cu-status.json','post-timing-host-build-specs.json','post-timing-guest-packages.json')

def canonical_grade_sha(grade):
    return hashlib.sha256(json.dumps(grade,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate_rationale_amendments(root,grades):
    """Check corrections against immutable original grades and actual finals."""
    path=root/'soak-results/review/rationale-amendments.json'
    if not path.exists():return None  # Fresh reproductions may need no corrections.
    amendments=read(path);rows=amendments['amendments'];by={g['job_id']:g for g in grades}
    assert len(rows)==len(RATIONALE_AMENDMENT_JOBS)
    assert {a['job_id'] for a in rows}==RATIONALE_AMENDMENT_JOBS
    for a in rows:
        g=by[a['job_id']]
        paths=list((root/'soak-results/runs'/a['job_id']/'runs').glob('*.json'))
        assert len(paths)==1
        assert a['record_sha256']==g['record_sha256']==sha(paths[0])
        assert a['original_grade_canonical_sha256']==canonical_grade_sha(g)
        assert a['original_rationale']==g['rationale']
        finals=[c['final'] for c in read(paths[0])['conversations']]
        assert len(finals)==1
        count=len(finals[0].split())
        assert count==a['final_whitespace_word_count'] and count<=a['maximum_words']==120
        assert a['components_unchanged'] is True and a['pass_and_failure_flags_unchanged'] is True
        assert a['human_semantic_adjudication_replaced'] is False
        assert g['components']['reporting']==.5 and a['corrected_rationale']!=g['rationale']
    return amendments

def bind_rationale_amendments(amendments,private_grades,public_grades,scrubber):
    old={g['job_id']:g for g in private_grades};new={g['job_id']:g for g in public_grades}
    clean=scrubber.value(amendments)
    for a in clean['amendments']:
        private=old[a['job_id']];public=new[a['job_id']]
        assert a['original_rationale']==public['rationale']
        for key in ['components','passed','critical_execution_failure','fabricated_evidence']:
            assert private[key]==public[key]
        a['as_tested_original_record_sha256']=a['record_sha256']
        a['record_sha256']=public['record_sha256']
        a['as_tested_original_grade_canonical_sha256']=a['original_grade_canonical_sha256']
        a['original_grade_canonical_sha256']=canonical_grade_sha(public)
    scrubber.check(clean)
    return clean

def bind_grade(grade, original_sha, public_sha, scrubber):
    if grade['record_sha256'] != original_sha:
        raise ValueError('Review refers to stale private evidence')
    clean=scrubber.value(grade)
    clean['as_tested_original_record_sha256']=original_sha
    clean['record_sha256']=public_sha
    scrubber.check(clean)
    return clean

def validate_supplement(root):
    folder=root/'restore-file-supplement-results';protocol=read(folder/'protocol.json')
    assert protocol['phase']=='restore-file-interface-supplement' and protocol['cases']==['B04'] and protocol['expected_trials']==15
    coverage=read(folder/'coverage.json');assert coverage['recorded_trials']==15 and not coverage['stopped']
    validation=read(folder/'interface-validation.json')
    assert len(validation)==3 and {x['variant'] for x in validation}=={0,1,2}
    assert all(x['unscored'] and x['wrong_target_rejected'] and x['extra_path_rejected'] for x in validation)
    grades=read(folder/'review/grades.json')
    expected={(m,'B04',v) for m in protocol['candidates'] for v in [0,1,2]}
    assert len(grades)==15 and len(expected)==15
    assert {(g['candidate'],g['case_id'],g['variant']) for g in grades}==expected
    paths=list((folder/'runs').glob('*.json'));assert len(paths)==15
    stops=critical_stops(root/'main-results')
    for grade in grades:
        path=folder/'runs'/f"B04-v{grade['variant']}-{grade['candidate']}.json";record=read(path)
        if record['status']=='screened_out':
            validate_screening_record(record,root/'main-results')
            assert not grade['passed'] and grade.get('review_status')=='unexecuted_screening_record'
        else:
            assert grade['candidate'] not in stops, 'Critically stopped candidate resumed in supplement'
            assert record['status']=='completed' and record['restoration_verified']
        assert grade['record_sha256']==sha(path)
    for name,digest in protocol['source_sha256'].items():assert sha(folder/'sources'/name)==digest

def validate(root):
    main=root/'main-results';p=read(main/'protocol.json')
    expected={(m,c,v) for m in p['candidates'] for c in p['cases'] for v in p['variants']}
    assert len(expected)==1200 and p['expected_trials']==1200
    for name,digest in p['source_sha256'].items():
        assert sha(main/'sources'/name)==digest, 'Archived comparison source changed'
    records,screening=validate_main(main)
    assert set(records)==expected, 'All declared comparison slots required'
    grades=read(main/'review/grades.json')
    assert len(grades)==1200
    assert {(g['candidate'],g['case_id'],g['variant']) for g in grades}==expected
    for g in grades:assert g['record_sha256']==sha(records[(g['candidate'],g['case_id'],g['variant'])])
    latency=root/'latency-results';rows=read(latency/'trials.json')
    keys=[(r['model'],r['condition'],r['trial']) for r in rows]
    required={(m,c,i) for m in p['candidates'] if m!='worker2b-planner9b'
              for c,n in [('warm',20),('fresh_load',10)] for i in range(n)}
    assert len(rows)==120 and len(set(keys))==120 and set(keys)==required
    assert (latency/'summary.json').exists()
    for name,digest in read(latency/'protocol.json')['source_sha256'].items():
        archived=latency/'sources'/name
        assert sha(archived if archived.exists() else root/name)==digest, 'Latency source changed before archival'
    soak=root/'soak-results';completion=read(soak/'completion.json');jobs=read(soak/'jobs.json')
    assert completion['complete'] and completion['elapsed_seconds']>=86400
    assert len(jobs)==301 and collections.Counter(j['kind'] for j in jobs)=={'routine':288,'fault':4,'queue':9}
    soak_grades=read(soak/'review/grades.json')
    assert len(soak_grades)==301 and len({g['job_id'] for g in soak_grades})==301
    assert {g['job_id'] for g in soak_grades}=={j['id'] for j in jobs}
    for grade in soak_grades:
        paths=list((soak/'runs'/grade['job_id']/'runs').glob('*.json'))
        assert len(paths)==1 and grade['record_sha256']==sha(paths[0])
    validate_rationale_amendments(root,soak_grades)
    assert (soak/'acceptance.json').exists(), 'Analyze semantic acceptance before publication'
    for name,digest in read(soak/'protocol.json')['source_sha256'].items():
        assert sha(soak/'sources'/name)==digest, 'Archived soak source changed'
    validate_supplement(root)
    validate_message_supplement(root)
    smoke=validate_smoke(root,root/'soak-selection.json',read(root/'soak-selection.json'))
    assert read(soak/'protocol.json')['production_gateway_smoke']==smoke, 'Soak preflight provenance changed'
    return records,grades,jobs,soak_grades

class Exporter:
    def __init__(self,destination,scrubber):
        self.destination=destination;self.scrubber=scrubber;self.manifest=[]

    def write(self,relative,data,original=None):
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Invalid public artifact path')
        self.scrubber.check(data.decode())
        path=self.destination/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        item={'path':str(relative),'bytes':len(data),'public_sha256':sha(path)}
        if original:item['as_tested_original_sha256']=sha(original)
        self.manifest.append(item)
        return item['public_sha256']

    def json(self,path,relative):
        return self.write(relative,json_bytes(self.scrubber.value(read(path))),path)

    def record(self,path,relative,main_stop_public_hashes=None):
        clean=sanitize_record(read(path),sha(path),self.scrubber)
        if clean.get('main_critical_stop'):
            assert main_stop_public_hashes is not None, 'Bind screening proof to public main evidence'
            stop=clean['main_critical_stop'];original=stop['record_sha256']
            stop['as_tested_original_record_sha256']=original
            stop['record_sha256']=main_stop_public_hashes[original]
        return self.write(relative,json_bytes(clean),path)

    def optional(self,folder,files,prefix):
        for name in files:
            path=folder/name
            if path.exists():self.json(path,prefix/name)

    def telemetry(self,path,relative):
        if path.suffix=='.jsonl':
            data=b''.join(json.dumps(self.scrubber.value(json.loads(line)),ensure_ascii=True).encode()+b'\n'
                          for line in path.read_text().splitlines() if line)
            self.write(relative,data,path)
        else:self.json(path,relative)

    def sources(self,folder,prefix):
        if not (folder/'sources').exists():return
        for path in sorted((folder/'sources').iterdir()):
            if not path.is_file() or path.suffix not in ['.py','.json','.ini','.service','.sh']:continue
            text=self.scrubber.string(path.read_text());self.write(prefix/'sources'/path.name,text.encode(),path)

def export(root,destination,rules):
    records,grades,jobs,soak_grades=validate(root)
    destination.mkdir(parents=True,exist_ok=False)
    scrubber=Scrubber(rules);out=Exporter(destination,scrubber)
    for phase in ['main-results','latency-results','soak-results','restore-file-supplement-results','message-prompt-supplement-results','soak-smoke-results']:
        folder=root/phase;prefix=Path(phase)
        out.sources(folder,prefix)
        out.optional(folder,[Path(n) for n in ['protocol.json','coverage.json','windows.json','completion.json','summary.json',
             'initial-state.json','final-state.json','runtime-configuration.json','final-snapshot-restoration.json',
             'production-recovery.json','schedule.json','jobs.json','acceptance.json','tool-latency-summary.json','interface-validation.json','prompt-validation.json','telemetry.json','kernel-query-validation.json']],prefix)
        if phase!='main-results':
            out.optional(folder,[Path('review/observability-notes.json')],prefix)
        for pattern in ['telemetry-*.json','production-recovery-*.json']:
            for path in sorted(folder.glob(pattern)):out.json(path,prefix/path.name)
        for name in ['telemetry.jsonl','queue-events.jsonl']:
            path=folder/name
            if path.exists():out.telemetry(path,prefix/name)
    public_grades=[];main_stop_public_hashes={}
    for grade in grades:
        path=records[(grade['candidate'],grade['case_id'],grade['variant'])]
        digest=out.record(path,Path('main-results/runs')/path.name)
        main_stop_public_hashes[sha(path)]=digest
        public_grades.append(bind_grade(grade,sha(path),digest,scrubber))
    out.write('main-results/review/grades.json',json_bytes(public_grades),root/'main-results/review/grades.json')
    out.optional(root/'main-results',[Path('review/observability-notes.json'),
                 Path('review/method.json')],Path('main-results'))
    public_soak=[]
    for grade in soak_grades:
        path=next((root/'soak-results/runs'/grade['job_id']/'runs').glob('*.json'))
        digest=out.record(path,Path('soak-results/runs')/grade['job_id']/'runs'/path.name)
        public_soak.append(bind_grade(grade,sha(path),digest,scrubber))
    out.write('soak-results/review/grades.json',json_bytes(public_soak),root/'soak-results/review/grades.json')
    amendment_path=root/'soak-results/review/rationale-amendments.json'
    if amendment_path.exists():
        amendment=bind_rationale_amendments(read(amendment_path),soak_grades,public_soak,scrubber)
        out.write('soak-results/review/rationale-amendments.json',json_bytes(amendment),amendment_path)
    smoke_folder=root/'soak-smoke-results';public_smoke=[]
    for grade in read(smoke_folder/'review/grades.json'):
        path=next((smoke_folder/'runs'/grade['job_id']/'runs').glob('*.json'))
        digest=out.record(path,Path('soak-smoke-results/runs')/grade['job_id']/'runs'/path.name)
        public_smoke.append(bind_grade(grade,sha(path),digest,scrubber))
    out.write('soak-smoke-results/review/grades.json',json_bytes(public_smoke),smoke_folder/'review/grades.json')
    out.json(root/'soak-selection.json',Path('soak-selection.json'))
    out.optional(root,[Path('phase-corrections.json')],Path('.'))
    out.optional(root,[Path(name) for name in POST_TIMING_FILES],Path('.'))
    supplement=root/'restore-file-supplement-results';public_supplement=[]
    for grade in read(supplement/'review/grades.json'):
        path=supplement/'runs'/f"B04-v{grade['variant']}-{grade['candidate']}.json"
        digest=out.record(path,Path('restore-file-supplement-results/runs')/path.name,main_stop_public_hashes)
        public_supplement.append(bind_grade(grade,sha(path),digest,scrubber))
    out.write('restore-file-supplement-results/review/grades.json',json_bytes(public_supplement),supplement/'review/grades.json')
    message=root/'message-prompt-supplement-results';public_message=[]
    for grade in read(message/'review/grades.json'):
        path=message/'runs'/f"A06-v{grade['variant']}-{grade['candidate']}.json"
        digest=out.record(path,Path('message-prompt-supplement-results/runs')/path.name,main_stop_public_hashes)
        public_message.append(bind_grade(grade,sha(path),digest,scrubber))
    out.write('message-prompt-supplement-results/review/grades.json',json_bytes(public_message),message/'review/grades.json')
    out.json(root/'latency-results/trials.json',Path('latency-results/trials.json'))
    for name in read(root/'latency-results/protocol.json')['source_sha256']:
        relative=Path('latency-results/sources')/name
        if (destination/relative).exists():continue
        source=root/name
        out.write(relative,scrubber.string(source.read_text()).encode(),source)
    for path in sorted((root/'latency-results').glob('*-prime.json')):out.json(path,Path('latency-results')/path.name)
    # Catalogs are recomputed from public SHA-bound records, not copied from
    # private catalogs that refer to the original transcript byte hashes.
    for name in ['catalog-results.py','catalog-reviewed.py']:
        module=runpy.run_path(str(root/name))
        module['catalog'](destination/'main-results')
    for path in sorted((destination/'main-results/catalog').iterdir()):
        scrubber.check(path.read_text())
        out.manifest.append({'path':str(path.relative_to(destination)),'bytes':path.stat().st_size,'public_sha256':sha(path)})
    # Single-case corrective findings are never pooled into the main index.
    runpy.run_path(str(root/'catalog-supplement.py'))['catalog'](destination)
    for path in sorted((destination/'restore-file-supplement-results/catalog').iterdir()):
        scrubber.check(path.read_text())
        out.manifest.append({'path':str(path.relative_to(destination)),'bytes':path.stat().st_size,'public_sha256':sha(path)})
    runpy.run_path(str(root/'catalog-supplement.py'))['catalog'](destination,'A06')
    for path in sorted((destination/'message-prompt-supplement-results/catalog').iterdir()):
        scrubber.check(path.read_text())
        out.manifest.append({'path':str(path.relative_to(destination)),'bytes':path.stat().st_size,'public_sha256':sha(path)})
    metadata={'schema_version':1,'frontier_parity':'uncalibrated','owner_workload_coverage':'unmeasured',
        'privacy_transform':'Known operator identities/addresses/credentials removed; physical host boot identifiers and test SSH fingerprints pseudonymized; grant values redacted. Original and public byte hashes distinguished. Review decisions, timings and equality/state predicates retained.',
        'review_evaluator':'independent Codex transcript review; no human/frontier calibration',
        'automated_redaction_counts':scrubber.stats,'files':sorted(out.manifest,key=lambda x:x['path']),
        'manual_privacy_review':'Required before uploading; an automated scrub is not proof of absence of identifying information.'}
    out.write('evidence-manifest.json',json_bytes(metadata))
    return metadata

def archive(folder,destination):
    # Explicit TarInfo avoids leaking filesystem owners, groups or absolute paths.
    with destination.open('xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w|') as tar:
        for path in sorted(folder.rglob('*')):
            if not path.is_file():continue
            if path.is_symlink():raise ValueError('Do not archive symlinks')
            info=tarfile.TarInfo(str(path.relative_to(folder)));info.size=path.stat().st_size
            info.mode=0o644;info.uid=info.gid=info.mtime=0;info.uname=info.gname=''
            with path.open('rb') as data:tar.addfile(info,data)
    if destination.stat().st_size>=95*1024**2:raise ValueError('Archive exceeds publication size ceiling; split before uploading')
    return {'bytes':destination.stat().st_size,'sha256':sha(destination)}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--private-rules',type=Path,required=True)
    parser.add_argument('--archive',type=Path);args=parser.parse_args()
    result=export(args.root,args.output,read(args.private_rules))
    print(json.dumps({'exported_files':len(result['files']),'frontier_parity':'uncalibrated','manual_privacy_review':'required'}))
    if args.archive:print(json.dumps(archive(args.output,args.archive)))
