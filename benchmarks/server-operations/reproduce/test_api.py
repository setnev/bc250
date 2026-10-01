"""Authenticated API acceptance check using the reproducer's private settings."""
import json, os, time, urllib.request

def request(path,payload=None,authenticated=True):
    headers={'Content-Type':'application/json'}
    if authenticated:headers['Authorization']='Bearer '+os.environ['BC250_API_KEY']
    req=urllib.request.Request(os.environ['BC250_BASE_URL'].rstrip('/')+path,headers=headers,data=json.dumps(payload).encode() if payload is not None else None)
    start=time.monotonic()
    with urllib.request.urlopen(req,timeout=180) as r:data=json.load(r)
    return data,round(time.monotonic()-start,3)
