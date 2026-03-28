# Integrations

The orchestrator supports service integration metadata in `integrations.yaml` for common API/web services.

Design goals:

- Default external access mode is `read`.
- `write` mode requires an explicit directive.
- Connector state stores references and scopes, not raw secrets.
- Login/docs links are exposed in the dashboard for quick operator flow.

## Built-in Service Catalog

Current defaults include:

- GitHub
- GitLab
- Slack
- Notion
- Proton Mail
- Proton Drive
- Proton VPN

You can extend `integrations.yaml` with additional services and scope guidance.

## Proton Services

Proton support is modeled around documented surfaces, not assumed private APIs.

- Proton Mail: use Proton Mail Bridge and approved mail clients for mailbox access. Proton documents Bridge startup and CLI guidance, but not a public general-purpose mail API.
- Proton Drive: use the official web, desktop, or mobile apps. Proton has documented Drive support and a Drive SDK preview, but not a general public production API for third-party orchestration.
- Proton VPN: use the official app, business admin surfaces, SSO/SCIM, and managed profile workflows. Proton does not document a public consumer API for direct tunnel control.

Source URLs:

- Proton Mail IMAP/SMTP and Bridge setup: https://proton.me/support/imap-smtp-and-pop3-setup
- Proton Mail Bridge startup guide: https://proton.me/support/automatically-start-bridge
- Proton Drive SDK preview: https://proton.me/blog/proton-drive-sdk-preview
- Proton Drive for Business support: https://proton.me/support/drive/proton-drive-for-business
- Proton VPN for Business support: https://proton.me/support/business/vpn
- Proton VPN business setup guide: https://proton.me/support/setup-vpn-business
- Proton VPN business product page: https://proton.me/business/vpn

## API Endpoints

- `GET /api/integrations`
- `POST /api/integrations/connect`
- `POST /api/integrations/mode`
- `POST /api/integrations/disconnect`

## CLI Commands

- `uv run python scripts/substrate_cli.py integrations`
- `uv run python scripts/substrate_cli.py integration-connect --service github --mode read`
- `uv run python scripts/substrate_cli.py integration-mode --service github --mode write --write-directive "..."`
- `uv run python scripts/substrate_cli.py integration-disconnect --service github`

## Example: Connect in Read Mode

```bash
curl -fsS -X POST http://127.0.0.1:8090/api/integrations/connect \
  -F service_id=github \
  -F auth_method=personal_access_token \
  -F token_ref=GITHUB_TOKEN \
  -F granted_scopes=read:org,read:project \
  -F access_mode=read
```

## Example: Escalate to Write Mode With Directive

```bash
curl -fsS -X POST http://127.0.0.1:8090/api/integrations/mode \
  -F service_id=github \
  -F access_mode=write \
  -F write_directive="Create release tag for approved build candidate"
```

Without `write_directive`, write mode changes are rejected.
