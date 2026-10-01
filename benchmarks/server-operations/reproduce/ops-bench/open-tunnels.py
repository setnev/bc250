"""Pinned host tunnels; keep this process alive for the whole lab run."""
from pathlib import Path
import subprocess, sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from remote import ssh_args

args=ssh_args();target=args.pop()
for local,remote in [(22219,22219),(22220,22220),(18120,18220),(18081,8080)]:args+=['-L',f'127.0.0.1:{local}:127.0.0.1:{remote}']
raise SystemExit(subprocess.run(args+['-N','-o','ExitOnForwardFailure=yes',target]).returncode)
