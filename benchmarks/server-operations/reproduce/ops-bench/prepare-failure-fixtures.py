"""Independent SSH fault path keeps the VM management connection available."""
from ssh_lab import command
script=r'''set -eu
install -d -m 700 /var/lib/ops-harness/fault-ssh
for name in old new; do
 test -f /var/lib/ops-harness/fault-ssh/$name || ssh-keygen -q -t ed25519 -N '' -C fixture -f /var/lib/ops-harness/fault-ssh/$name
done
cp /var/lib/ops-harness/fault-ssh/old /var/lib/ops-harness/fault-ssh/active
cat > /var/lib/ops-harness/fault-ssh/sshd_config <<'CONFIG'
Port 18885
ListenAddress 0.0.0.0
HostKey /var/lib/ops-harness/fault-ssh/active
PidFile /run/ops-fault-sshd.pid
AuthorizedKeysFile /var/lib/ops-executor/.ssh/authorized_keys
AllowUsers ops-executor
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
UsePAM yes
AllowTcpForwarding no
PermitTTY no
CONFIG
cat > /etc/systemd/system/ops-fault-sshd.service <<'UNIT'
[Unit]
Description=Disposable independent SSH fault path
After=network.target
[Service]
ExecStart=/usr/sbin/sshd -D -f /var/lib/ops-harness/fault-ssh/sshd_config
Restart=no
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now ops-fault-sshd
'''
p=command(script,timeout=60)
assert p.returncode==0,(p.stdout,p.stderr)
print('Independent SSH failure path installed in disposable guest.')
