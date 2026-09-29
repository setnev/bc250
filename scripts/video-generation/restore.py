import pathlib,json,subprocess
R=pathlib.Path(__file__).parent;p=R/'restore-state.json'
if p.exists():
 s=json.loads(p.read_text())
 for path,value in s['cpu_governors'].items():pathlib.Path(path).write_text(value)
 subprocess.run(['python3','/usr/local/libexec/bc250-profile-clock.py','restore'],check=True)
 if s['services']:subprocess.run(['systemctl','start',*s['services']],check=True)
 p.unlink()
