"""Generate private reference configs without altering existing system services."""
from pathlib import Path
import argparse, json, secrets

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    dest=args.output.resolve()
    if ROOT.parent in dest.parents or dest==ROOT.parent:raise RuntimeError('Generate API credentials outside the repository')
    dest.mkdir(mode=0o700,parents=True,exist_ok=False)
    reference=json.loads((ROOT/'reproduction-runtime-config.json').read_text())
    for name,content in [('profiles.json',reference['profile_template']),('gateway.json',reference['gateway_template'])]:
        (dest/name).write_text(json.dumps(content,indent=2)+'\n');(dest/name).chmod(0o600)
    (dest/'api-key').write_text(secrets.token_urlsafe(48)+'\n');(dest/'api-key').chmod(0o600)
    print('Private reference configs and a fresh API key generated outside the repository; no system config changed.')

if __name__=='__main__':main()
