"""Distinct package and identity artifacts for the three frozen fault variants."""
from ssh_lab import command
script=r'''set -eu
systemctl mask --now apt-daily.timer apt-daily.service apt-daily-upgrade.timer apt-daily-upgrade.service unattended-upgrades.service fwupd-refresh.timer update-notifier-download.timer
for role in old new unexpected; do
 cp /var/lib/ops-harness/identity/$role /var/lib/ops-harness/identity/$role-v0
 cp /var/lib/ops-harness/identity/$role.pub /var/lib/ops-harness/identity/$role-v0.pub
 for variant in 1 2; do
  path=/var/lib/ops-harness/identity/$role-v$variant
  test -f "$path" || ssh-keygen -q -t ed25519 -N '' -C fixture -f "$path"
 done
done
for version in 1.3 1.4; do
 pkg=/opt/ops-lab/packages/build-$version
 install -d "$pkg/DEBIAN" "$pkg/usr/share/ops-fixture"
 sed "s/Version: 1.1/Version: $version/" /opt/ops-lab/packages/build-1.1/DEBIAN/control > "$pkg/DEBIAN/control"
 printf '%s\n' "$version" > "$pkg/usr/share/ops-fixture/version"
 dpkg-deb --build "$pkg" /opt/ops-lab/packages/ops-fixture-package_$version.deb
done
'''
p=command(script,timeout=60);assert p.returncode==0,(p.stdout,p.stderr)
print('Distinct package versions and SSH fingerprints provisioned for all three variants.')
