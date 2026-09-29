"""Analyze finished trials without treating frame changes as a quality score."""
import pathlib,json,re,statistics,hashlib,sys
R=pathlib.Path(__file__).parent;folder=sys.argv[1] if len(sys.argv)>1 else 'results'
assert folder in ('results','diagnostic-results')
O=R/folder
rows=json.loads((O/'trials.json').read_text())
for row in rows:
 p=O/row['label'];log=(p/'runtime.log').read_text(errors='replace')
 for field,pattern in [('sampling_seconds',r'sampling completed, taking ([0-9.]+)s'),('decode_seconds',r'decode_first_stage completed, taking ([0-9.]+)s'),('engine_seconds',r'generate_video completed in ([0-9.]+)s')]:
  found=re.findall(pattern,log)
  row[field]=float(found[-1]) if found else None
 if (p/'frames.md5').exists():
  hashes=[x.split(',')[-1].strip() for x in (p/'frames.md5').read_text().splitlines() if x and not x.startswith('#')]
  row['unique_frames']=len(set(hashes));row['frame_sequence_sha256']=hashlib.sha256('\n'.join(hashes).encode()).hexdigest()
for model in ['wan21','wan22']:
 a=next((r for r in rows if r['label']==model+'-car-1'),None);b=next((r for r in rows if r['label']==model+'-car-2'),None)
 if a and b:b['matches_first_frame_sequence']=b.get('frame_sequence_sha256')==a.get('frame_sequence_sha256')
(O/'analysis.json').write_text(json.dumps(rows,indent=2));print(json.dumps([{k:r.get(k) for k in ['label','process_seconds','sampling_seconds','decode_seconds','peak_edge_c','unique_frames','matches_first_frame_sequence']} for r in rows],indent=2))
