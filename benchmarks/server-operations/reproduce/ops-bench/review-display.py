"""Compact transcript presentation; no inferred success or automatic grading.

Original evidence remains in review bundles and raw records. The selected nested
fields below shorten repeated fixture data, retaining the full final reports,
tool order, arguments, errors and relevant observed state for manual review.
"""
from pathlib import Path
import argparse, json

def present(result):
    if 'timer' in result and 'integrity' in result:
        return {**{k:v for k,v in result.items() if k!='timer'},
                'timer_status':result['timer']['status'],
                'timer_configuration':result['timer']['configuration'],
                'timer_logs':result['timer']['logs']}
    if 'artifact_inventory' in result:
        return {**{k:v for k,v in result.items() if k not in ['artifact_inventory','artifact_policy']},
                'artifact_inventory':{k:{n:v for n,v in item.items() if n!='observed_sha256'} for k,item in result['artifact_inventory'].items()},
                'artifact_policy':{k:v for k,v in result['artifact_policy'].items() if k!='approved_artifacts'},
                'omitted_from_display':'literal executable SHA strings; full values retained in raw bundle'}
    return result

def display(bundle,candidate=None,variant=None):
    print(json.dumps({'case_id':bundle['case_id'],'requirements':bundle['frozen_rubric']['case_specific_requirements'],'inapplicable':bundle['frozen_rubric']['inapplicable_components'],'trial_count':len(bundle['trials'])}))
    for trial in bundle['trials']:
        if candidate and trial['candidate']!=candidate:continue
        if variant is not None and trial['variant']!=variant:continue
        print(json.dumps({k:trial[k] for k in ['candidate','variant','checks','counters','failures']}))
        seen={}
        for i,event in enumerate(trial['observations']):
            if event.get('tool'):
                value={'model':event.get('model'),'tool':event['tool'],'arguments':event['arguments'],'result':present(event['result'])}
            else:value=event
            key=json.dumps(value,sort_keys=True)
            if key in seen:print(json.dumps({'event':i,'identical_to_display_event':seen[key]}));continue
            seen[key]=i;print(json.dumps({'event':i,**value}))
        print(json.dumps({'intermediate_assistant_text':trial['intermediate_assistant_text'],'finals':trial['finals']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('bundle',type=Path)
    parser.add_argument('--candidate');parser.add_argument('--variant',type=int)
    args=parser.parse_args();display(json.loads(args.bundle.read_text()),args.candidate,args.variant)
