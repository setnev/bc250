"""Keep corrective single-task evidence separate from the frozen 80-case index."""
from pathlib import Path
import argparse, hashlib, json, statistics
from score import outcome_quality
from screening_policy import validate_screening_record, critical_stops


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reviewed_trials(folder, candidates, case_id='B04'):
    grades = json.loads((folder / 'review/grades.json').read_text())
    selected = [g for g in grades if g['case_id'] == case_id]
    expected = {(c, v) for c in candidates for v in range(3)}
    observed = {(g['candidate'], g['variant']) for g in selected}
    if observed != expected or len(selected) != len(expected):
        raise ValueError(case_id+' comparison requires all five candidates and three reviewed variants')
    rows = []
    stops=critical_stops(folder.parent/'main-results') if folder.name!='main-results' else {}
    for grade in selected:
        path = folder / 'runs' / f"{case_id}-v{grade['variant']}-{grade['candidate']}.json"
        record = json.loads(path.read_text())
        if grade['record_sha256'] != digest(path):
            raise ValueError('Stale '+case_id+' review evidence')
        if record['status']=='screened_out':
            validate_screening_record(record,folder.parent/'main-results')
            assert not grade['passed'] and grade.get('review_status')=='unexecuted_screening_record'
            rows.append({**grade,'executed':False,'absolute_trial_quality':None,'actual_state_passed':None,'agent_seconds':None})
            continue
        if record['status'] != 'completed' or not record['restoration_verified']:
            raise ValueError(case_id+' trial is not completed and restored')
        assert grade['candidate'] not in stops, 'Critically stopped candidate resumed in supplement'
        rows.append({**grade, 'executed':True,'absolute_trial_quality': outcome_quality(grade),
                     'actual_state_passed': record['independent_checks']['state_outcome_passed'],
                     'agent_seconds': record['agent_seconds']})
    return rows


def catalog(root, case_id='B04'):
    if case_id not in ['B04','A06']:raise ValueError('Unknown supplemental comparison')
    supplement = root / ('restore-file-supplement-results' if case_id=='B04' else 'message-prompt-supplement-results')
    protocol = json.loads((supplement / 'protocol.json').read_text())
    candidates = protocol['candidates']
    if len(candidates) != 5 or len(set(candidates)) != 5:
        raise ValueError('Expected five distinct candidates')
    if digest(Path(__file__).with_name('score.py')) != protocol['source_sha256']['score.py']:
        raise ValueError('Scoring implementation differs from frozen supplemental protocol')
    original = reviewed_trials(root / 'main-results', candidates, case_id)
    corrected = reviewed_trials(supplement, candidates, case_id)
    comparisons = []
    for candidate in candidates:
        entry = {'candidate': candidate}
        labels=['original_interface','corrected_read_interface'] if case_id=='B04' else ['original_prompt','clarified_prompt']
        for label, rows in zip(labels,[original,corrected]):
            slots = [r for r in rows if r['candidate'] == candidate]
            trials = [r for r in slots if r['executed']]
            entry[label] = {
                'reviewed_declared_slots':len(slots),'screened_unexecuted_slots':len(slots)-len(trials),
                'reviewed_trials': len(trials), 'semantic_passes': sum(r['passed'] for r in trials),
                'actual_state_passes': sum(r['actual_state_passed'] for r in trials),
                'mean_absolute_trial_quality': statistics.mean(r['absolute_trial_quality'] for r in trials) if trials else None,
                'median_agent_seconds': statistics.median(r['agent_seconds'] for r in trials) if trials else None,
                'apparatus_limitations': sorted({a for r in trials for a in r.get('apparatus_limitations', [])}),
                'fabricated_evidence_runs': sum(r['fabricated_evidence'] for r in trials),
                'component_means': {k: statistics.mean(r['components'][k] for r in trials)
                                    for k in trials[0]['components']} if trials else None}
        comparisons.append(entry)
    result = {'case_id': case_id, 'frontier_parity': 'uncalibrated',
              'scope': 'Single corrective task comparison; not an aggregate administrator score or role qualification.',
              'comparison_limit': protocol['comparison_limit'],
              'pooling': 'Separate phase. Original 1200-declared-slot grades and any eligible index remain unchanged.',
              'candidates': comparisons}
    destination = supplement / 'catalog'
    destination.mkdir(exist_ok=True)
    (destination / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--case',choices=['B04','A06'],default='B04')
    args=parser.parse_args();print(json.dumps(catalog(args.root,args.case), indent=2))
