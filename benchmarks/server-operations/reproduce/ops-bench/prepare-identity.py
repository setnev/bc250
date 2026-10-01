"""Install disposable authentication fixtures; no private key leaves the VM."""
from ssh_lab import command
script=r'''set -eu
install -d -m 700 /var/lib/ops-harness/identity
for name in old new unexpected; do
 test -f /var/lib/ops-harness/identity/$name || ssh-keygen -q -t ed25519 -N '' -C fixture -f /var/lib/ops-harness/identity/$name
done
install -d -m 700 -o ops-test-account -g ops-test-account /home/ops-test-account/.ssh
ssh-keyscan -t ed25519 127.0.0.1 > /var/lib/ops-harness/identity/known_hosts 2>/dev/null
cat > /etc/systemd/system/ops-token.service <<'UNIT'
[Unit]
Description=Disposable authenticated token endpoint
[Service]
ExecStart=/usr/bin/python3 /opt/ops-lab/identity-fixture.py serve
Restart=no
UNIT
pkg=/opt/ops-lab/packages/build-1.2-failed
cp -a /opt/ops-lab/packages/build-1.1 "$pkg"
sed -i 's/Version: 1.1/Version: 1.2/' "$pkg/DEBIAN/control"
printf '#!/bin/sh\nexit 42\n' > "$pkg/DEBIAN/postinst"
chmod 755 "$pkg/DEBIAN/postinst"
dpkg-deb --build "$pkg" /opt/ops-lab/packages/ops-fixture-package_1.2-failed.deb
systemctl daemon-reload
'''
p=command(script,timeout=60)
assert p.returncode==0,(p.stdout,p.stderr)
print('Actual disposable SSH keys, token service and failing package provisioned.')
