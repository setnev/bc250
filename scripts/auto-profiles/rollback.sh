#!/bin/bash
set -euo pipefail
backup=/etc/bc250-ai/before-auto-profiles
test -f "$backup/models.ini"
systemctl stop bc250-api-gateway.service bc250-ai.service bc250-profile-controller.service
systemctl disable bc250-api-gateway.service bc250-profile-controller.service
rm -f /etc/systemd/system/bc250-ai.service.d/30-profile-backend.conf
cp "$backup/models.ini" /etc/bc250-ai/models.ini
systemctl daemon-reload
systemctl enable --now bc250-gpu-tuning.service
systemctl start bc250-ai.service
