#!/bin/bash
set -euo pipefail
systemctl stop bc250-api-gateway bc250-ai bc250-profile-controller
install -m 644 /opt/bc250-mod-prep/cpu-power/before/controller.py /usr/local/libexec/bc250-profile-controller.py
install -m 644 /opt/bc250-mod-prep/cpu-power/before/gateway.py /usr/local/libexec/bc250-api-gateway.py
install -m 644 /opt/bc250-mod-prep/cpu-power/before/bc250-profile-controller.service /etc/systemd/system/bc250-profile-controller.service
systemctl daemon-reload
systemctl start bc250-profile-controller bc250-ai bc250-api-gateway
