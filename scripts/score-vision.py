import json,pathlib,re,statistics
ROOT=pathlib.Path(__file__).parent
cases=json.loads((ROOT/'cases.json').read_text())
def parse(s, semantic=False):
 s=re.sub(r'^```(?:json)?\s*|\s*```$','',s.strip(),flags=re.I)
 try:
  value=json.loads(s)
  if semantic and isinstance(value,list) and value and all(v==value[0] for v in value):value=value[0]
  return value if isinstance(value,dict) else {}
 except ValueError:return {}
def equal(a,b):
 if isinstance(a,dict) and isinstance(b,str) and set(a)=={"color","shape"}:a=str(a["color"])+" "+str(a["shape"])
 if isinstance(b,str):return isinstance(a,str) and ' '.join(a.split()).casefold()==' '.join(b.split()).casefold()
 if isinstance(b,list):return isinstance(a,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
 return type(a)==type(b) and a==b or isinstance(b,(int,float)) and not isinstance(b,bool) and not isinstance(a,bool) and a==b
summary={}
for p in sorted((ROOT/'results').glob('*results.json')):
 rows=json.loads(p.read_text());name=p.name.removesuffix('-results.json');scored=[]
 for c in cases:
  for row in [r for r in rows if r['label'].startswith(c['id']+'-')]:
   answer=parse(row['answer']); fields={k:equal(answer.get(k),v) for k,v in c['expected'].items()};semantic=parse(row['answer'],True); semantic_fields={k:equal(semantic.get(k),v) for k,v in c['expected'].items()};scored.append(dict(label=row['label'],correct=sum(fields.values()),total=len(fields),fields=fields,semantic_correct=sum(semantic_fields.values())))
 def metrics(sub):
  return dict(count=len(sub),mean_wall_seconds=statistics.mean(r['wall_seconds'] for r in sub),mean_first_content_seconds=statistics.mean(r['first_content_seconds'] for r in sub),mean_decode_tps=statistics.mean(r['timings']['predicted_per_second'] for r in sub)) if sub else {}
 summary[name]={'requests':len(rows),'first_requests':metrics([r for r in rows if r['label'].endswith('repeat1')]),'warm_repeats':metrics([r for r in rows if r['label'].endswith(('repeat2','repeat3'))]),'first_score':sum(s['correct'] for s in scored if s['label'].endswith('repeat1')),'first_total':sum(s['total'] for s in scored if s['label'].endswith('repeat1')),'first_semantic_score':sum(s['semantic_correct'] for s in scored if s['label'].endswith('repeat1')),'all_score':sum(s['correct'] for s in scored),'all_total':sum(s['total'] for s in scored),'scored':scored,'conversation':[{'label':r['label'],'answer':r['answer'],'wall_seconds':r['wall_seconds'],'first_content_seconds':r['first_content_seconds'],'decode_tps':r['timings']['predicted_per_second']} for r in rows if r['label'].startswith('conversation')]}
(ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for name,s in summary.items():print(name,s['requests'],s['first_score'],s['first_total'],s['first_requests'],s['warm_repeats']);print(s['conversation'])
