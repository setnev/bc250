import hashlib,json,pathlib,urllib.request
root=pathlib.Path(__file__).parent
(root/'models').mkdir(exist_ok=True)
for m in json.loads((root/'download-manifest.json').read_text()):
 p=root/'models'/m['local_name']
 if not p.exists():
  url=f"https://huggingface.co/{m['repo']}/resolve/{m['revision']}/{m['filename']}"
  print('Downloading',m['local_name'],flush=True)
  urllib.request.urlretrieve(url,str(p)+'.part')
  pathlib.Path(str(p)+'.part').rename(p)
 assert p.stat().st_size==m['bytes']
 assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==m['sha256']
 print('Verified',m['local_name'],flush=True)
(root/'downloads-complete.txt').write_text('All hashes verified\n')
