"""Restore the saved CPU governors, SMU override and production service states."""
import pathlib,json,subprocess
root=pathlib.Path(__file__).resolve().parent
state=root/'restore-state.json'
if state.exists():
 saved=json.loads(state.read_text())
 for path,value in saved['cpu_governors'].items():pathlib.Path(path).write_text(value)
 subprocess.run(['python3','/usr/local/libexec/bc250-profile-clock.py','restore'],check=True)
 if saved['services']:subprocess.run(['systemctl','start',*saved['services']],check=True)
 state.unlink()
 print('Production service and governor restoration completed.',flush=True)
