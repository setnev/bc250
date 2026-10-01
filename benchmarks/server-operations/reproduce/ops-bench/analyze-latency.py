"""Latency and exact requested tool emission are distinct measured properties."""
from pathlib import Path
import argparse, collections, json, math, statistics

def percentile(values):
    values=sorted(values)
    return values[max(0,math.ceil(.95*len(values))-1)] if values else None

def tool_emission(output):
    calls=output.get('tool_calls') or []
    if len(calls)!=1:return {'valid':False,'reason':'Expected exactly one tool call'}
    call=calls[0]
    if call.get('type')!='function' or call.get('function',{}).get('name')!='inspect':
        return {'valid':False,'reason':'Expected inspect function'}
    try:arguments=json.loads(call['function']['arguments'])
    except (KeyError,TypeError,json.JSONDecodeError):return {'valid':False,'reason':'Malformed tool arguments'}
    if arguments!={'target':'lab-01','resource':'service'}:
        return {'valid':False,'reason':'Wrong target/resource or extra arguments'}
    return {'valid':True,'reason':'Exact requested read-only service inspection'}

def analyze(rows,models):
    results=[]
    for model in models:
        for condition,expected in [('warm',20),('fresh_load',10)]:
            subset=[r for r in rows if r['model']==model and r['condition']==condition]
            delta=[];valid_delta=[];valid_completion=[];failures=collections.Counter();valid=0
            for row in subset:
                if row['status']!='completed':failures['request_failed']+=1;continue
                metrics=row['metrics'];first=metrics.get('first_content_or_tool_delta_seconds')
                if first is not None:delta.append(first)
                emission=tool_emission(row['output'])
                if not emission['valid']:failures[emission['reason']]+=1;continue
                valid+=1
                if first is not None:valid_delta.append(first)
                if metrics.get('seconds') is not None:valid_completion.append(metrics['seconds'])
            results.append({'model':model,'condition':condition,'expected_trials':expected,'recorded_trials':len(subset),
                'valid_tool_emission_count':valid,'request_or_tool_failures':dict(failures),
                'first_response_samples':len(delta),'first_response_median_seconds':statistics.median(delta) if delta else None,
                'first_response_p95_seconds':percentile(delta),'valid_tool_first_response_samples':len(valid_delta),
                'valid_tool_first_response_median_seconds':statistics.median(valid_delta) if valid_delta else None,
                'valid_tool_first_response_p95_seconds':percentile(valid_delta),
                'valid_complete_tool_response_samples':len(valid_completion),
                'valid_complete_tool_response_median_seconds':statistics.median(valid_completion) if valid_completion else None,
                'valid_complete_tool_response_p95_seconds':percentile(valid_completion),
                'finish_reason_counts':dict(collections.Counter(r.get('metrics',{}).get('finish_reason','unavailable') for r in subset)),
                'cached_prompt_tokens':[r.get('metrics',{}).get('timings',{}).get('cache_n') for r in subset if r.get('metrics',{}).get('timings')],
                'metric_note':'First response is the first nonempty content/tool delta. Complete tool response is the completed streamed message, including its valid full JSON. These are emission timings; the guest tool is not executed by the latency probe.',
                'percentile_method':'Nearest rank ceil(0.95*N); missing samples are reported, not treated as zero.'})
    return results

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);args=parser.parse_args()
    rows=json.loads((args.folder/'trials.json').read_text());protocol=json.loads((args.folder/'protocol.json').read_text())
    result=analyze(rows,protocol['models'])
    (args.folder/'tool-latency-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
