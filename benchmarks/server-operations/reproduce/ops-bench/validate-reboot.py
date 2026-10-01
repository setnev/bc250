"""Guest-only approved reboot, pinned reconnect and independent recovery checks."""
from pathlib import Path
import json,time
from ssh_lab import command
r=Path(__file__).resolve().parent
def reset(case):
 p=command(f'python3 /opt/ops-lab/fixture-reset.py {case} 0\n',timeout=90);assert p.returncode==0,(p.stdout,p.stderr)
reset('M03')
p=command('systemctl add-wants multi-user.target ops-token.service\ncat /proc/sys/kernel/random/boot_id\npython3 /opt/ops-lab/issue-grant.py reboot_lab \'{}\'\n')
assert p.returncode==0,p.stderr
lines=p.stdout.strip().splitlines();before=lines[-2];token=lines[-1]
q={'name':'apply_runbook','arguments':{'target':'lab-01','action':'reboot_lab','approval':token}}
reply=command(q,executor=True);out=json.loads(reply.stdout);assert out.get('scheduled'),out
start=time.monotonic();new=None;observed_disconnect=False
while time.monotonic()-start<90:
 time.sleep(2)
 p=command('cat /proc/sys/kernel/random/boot_id\n',timeout=12)
 if p.returncode:observed_disconnect=True;continue
 if p.stdout.strip()!=before:new=p.stdout.strip();break
assert new and observed_disconnect,'Reboot or transient loss was not independently observed'
p=command('systemctl is-active ops-demo nginx ops-lab-dns ops-token\ncurl -fsS http://127.0.0.1:18880/health\n',timeout=30)
assert p.returncode==0 and p.stdout.strip().endswith('OPS_LAB_V0_OK') and p.stdout.count('active\n')==4,(p.stdout,p.stderr)
record={'cases':['M03','F07'],'apparatus_passed':True,'new_guest_boot_verified':True,'disconnect_observed':True,'pinned_reconnect_succeeded':True,'application_and_dependencies_healthy':True,'recovery_seconds':time.monotonic()-start}
(r/'reboot-validation.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
reset('N01')
