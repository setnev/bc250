"""Prepare a synthetic CA and valid/expired TLS fixtures inside the lab VM."""
from ssh_lab import command
script=r'''set -eu
pki=/var/lib/ops-harness/pki
install -d -m 700 "$pki" "$pki/newcerts"
touch "$pki/index.txt"
printf '1000\n' > "$pki/serial"
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -keyout "$pki/ca.key" -out "$pki/ca.crt" -subj /CN=OperationsLabCA >/dev/null 2>&1
openssl req -new -newkey rsa:2048 -nodes -keyout "$pki/server.key" -out "$pki/server.csr" -subj /CN=ops.test -addext subjectAltName=DNS:ops.test >/dev/null 2>&1
openssl x509 -req -in "$pki/server.csr" -CA "$pki/ca.crt" -CAkey "$pki/ca.key" -CAcreateserial -days 30 -copy_extensions copy -out "$pki/valid.crt" >/dev/null 2>&1
cat > "$pki/ca.conf" <<'CONF'
[ca]
default_ca = fixture_ca
[fixture_ca]
database = /var/lib/ops-harness/pki/index.txt
new_certs_dir = /var/lib/ops-harness/pki/newcerts
certificate = /var/lib/ops-harness/pki/ca.crt
private_key = /var/lib/ops-harness/pki/ca.key
serial = /var/lib/ops-harness/pki/serial
default_md = sha256
default_days = 30
policy = fixture_policy
copy_extensions = copy
unique_subject = no
[fixture_policy]
commonName = supplied
CONF
openssl ca -batch -config "$pki/ca.conf" -in "$pki/server.csr" -startdate 20000101000000Z -enddate 20000102000000Z -out "$pki/expired.crt" >/dev/null 2>&1
cp "$pki/valid.crt" /var/lib/ops-harness/certificate-baseline.crt
cp "$pki/server.key" /var/lib/ops-harness/certificate-baseline.key
cp "$pki/valid.crt" /var/lib/ops-lab/server.crt
cp "$pki/server.key" /var/lib/ops-lab/server.key
cp "$pki/ca.crt" /var/lib/ops-lab/ca.crt
chmod 600 /var/lib/ops-lab/server.key
openssl verify -CAfile "$pki/ca.crt" "$pki/valid.crt"
if openssl verify -CAfile "$pki/ca.crt" "$pki/expired.crt"; then exit 1; fi
'''
p=command(script,timeout=90)
assert p.returncode==0,(p.stdout,p.stderr)
print('Synthetic valid certificate verifies; expired certificate correctly fails validation.')
