# OpenClaw Substrate Export (Full Access)
Generated: 2026-04-24 UTC
Mode: FULL (includes required gateway secret)

## Environment Identity
- Host name: opencrow
- Private IP: 10.128.0.2
- Public IP: 34.173.227.78
- Public URL: https://ocrow.34-173-227-78.sslip.io/
- GCP project id: gen-lang-client-0428623541
- GCP project number: 538316821392
- Zone: us-central1-f
- Region: us-central1
- Machine type: t2a-standard-2
- OS image: Debian 12 (bookworm) ARM64

## OpenClaw Runtime
- Version: OpenClaw 2026.4.23 (a979721)
- Service: openclaw-gateway.service
- Service file: /etc/systemd/system/openclaw-gateway.service
- Drop-in: /etc/systemd/system/openclaw-gateway.service.d/10-gateway-auth.conf
- Binary: /home/ahronzombi/.npm-global/bin/openclaw
- Config: /home/ahronzombi/.openclaw/openclaw.json
- Env file: /etc/openclaw/openclaw-gateway.env
- Gateway bind/port: loopback 127.0.0.1:18789 (proxied by Caddy)
- Gateway auth mode: password
- Device-auth hardening: enabled (dangerouslyDisableDeviceAuth=false)

## Reverse Proxy / TLS
- Caddy config: /etc/caddy/Caddyfile
- Proxy target: 127.0.0.1:18789
- TLS issuer: Let's Encrypt (via Caddy auto-ACME)
- Cert path root: /var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org-directory/

## Core State Paths
- Agent auth profiles: /home/ahronzombi/.openclaw/agents/main/agent/auth-profiles.json
- Agent auth state: /home/ahronzombi/.openclaw/agents/main/agent/auth-state.json
- Sessions: /home/ahronzombi/.openclaw/agents/main/sessions
- Pairing state: /home/ahronzombi/.openclaw/devices/paired.json
- Pending pair approvals: /home/ahronzombi/.openclaw/devices/pending.json
- WhatsApp credentials/session state: /home/ahronzombi/.openclaw/credentials/whatsapp/main

## SSH / Admin Access
- Primary admin Linux user: ahron (passwordless sudo)
- Service owner user: ahronzombi
- SSH command:
  gcloud compute ssh --zone "us-central1-f" "opencrow" --project "gen-lang-client-0428623541"

## Service Ops Commands
- Restart OpenClaw:
  sudo systemctl restart openclaw-gateway
- OpenClaw status:
  sudo systemctl status openclaw-gateway --no-pager -l
- OpenClaw logs:
  sudo journalctl -u openclaw-gateway -f
- OpenClaw app logs:
  sudo -iu ahronzombi /home/ahronzombi/.npm-global/bin/openclaw logs --follow
- Caddy status:
  sudo systemctl status caddy --no-pager -l
- Caddy logs:
  sudo journalctl -u caddy -f
- Local port/process map:
  sudo ss -tulpn

## Operational Risks to Fix Next
1. gateway.trustedProxies is unset while using reverse proxy.
2. gateway.allowRealIpFallback=true (should usually be false).
3. /home/ahronzombi/.openclaw/credentials is mode 755 (recommended 700).
4. GCP default-allow-ssh permits 0.0.0.0/0 (tighten when ready).

## Backup / Recovery
- OpenClaw config backups:
  - /home/ahronzombi/.openclaw/openclaw.json.bak
  - /home/ahronzombi/.openclaw/openclaw.json.pre-password-migration.20260424-225840.bak
- Disk snapshot policy: default-schedule-1 (daily, 14-day retention)
- WhatsApp recovery: restore /home/ahronzombi/.openclaw/credentials/whatsapp/main then restart openclaw-gateway.

## Notes
- Public UI currently returns Unauthorized unless authenticated.
- New devices still require pairing approval.
