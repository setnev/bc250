from pathlib import Path
import shlex
from ssh_lab import command,upload
root=Path(__file__).resolve().parent
for filename in ['policy.py','evidence.py','runbook_actions.py','transport-faults.py','task_registry.py','vm_executor.py']:upload(root/filename,'/opt/ops-lab/'+filename)
key=(root/'lab-private/executor_key.pub').read_text().strip()
s='''set -eu
id ops-executor >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/ops-executor --shell /bin/sh ops-executor
install -d -m 700 -o ops-executor -g ops-executor /var/lib/ops-executor/.ssh
printf '%s\\n' '''+shlex.quote('restrict,command="sudo -n /usr/bin/python3 /opt/ops-lab/vm_executor.py" '+key)+''' > /var/lib/ops-executor/.ssh/authorized_keys
chown ops-executor:ops-executor /var/lib/ops-executor/.ssh/authorized_keys
chmod 600 /var/lib/ops-executor/.ssh/authorized_keys
printf '%s\\n' 'ops-executor ALL=(root) NOPASSWD: /usr/bin/python3 /opt/ops-lab/vm_executor.py' > /etc/sudoers.d/ops-executor
chmod 440 /etc/sudoers.d/ops-executor
visudo -cf /etc/sudoers.d/ops-executor
'''
p=command(s);assert p.returncode==0,p.stderr
print('Forced-command executor installed inside disposable guest.')
print(command({'name':'inspect','arguments':{'target':'lab-01','resource':'service'}},executor=True).stdout)
