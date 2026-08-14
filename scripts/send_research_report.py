#!/usr/bin/env python3
"""Send the Proton Mail integration research report via Bridge SMTP."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

msg = MIMEMultipart("alternative")
msg["From"] = "ahronzombi@protonmail.com"
msg["To"] = "ahronzombi@protonmail.com"
msg["Subject"] = "Proton Mail Integration Research Report — Kilo/OpenClaw"

text = """\
PROTON MAIL INTEGRATION RESEARCH REPORT
Kilo Substrate & OpenClaw — August 13, 2026

EXECUTIVE SUMMARY
After deep research, Proton Mail Bridge is the recommended integration path for both
sending and receiving email from Kilo and OpenClaw.

1. INTEGRATION OPTIONS EVALUATED
- Proton Mail Bridge (IMAP/SMTP): RECOMMENDED -- local, E2E encrypted, already deployed
- Proton SMTP Submission (smtp.ch:587): Good fallback for outbound only, not E2E
- Proton Mail API: Does not exist (no public general-purpose API)
- OpenClaw Hooks: Has Gmail preset; can build custom Proton adapter
- Third-party IMAP pollers: Works with Bridge for receive path

2. CURRENT STATUS (FIXED THIS SESSION)
- Found: Bridge running with 0 accounts (keychain init failure at boot)
- Fixed: Restarted bridge, keychain now working, 1 account loaded
- SMTP 127.0.0.1:1025: Working (STARTTLS)
- IMAP 127.0.0.1:1143: Working (STARTTLS, IDLE capable)

3. SECURITY VALIDATION
- PASS: Ports bound to localhost only
- PASS: Vault encrypted via SecretService keychain
- PASS: STARTTLS on both SMTP and IMAP
- PASS: Keychain (gnome-keyring) functional and unlocked
- PASS: Bridge account loaded and syncing
- WARNING: Gmail credentials in plaintext in approval_lane.json -- needs removal
- PASS: OpenClaw hook system has strong security (token auth, prompt injection protection)

4. ACTION ITEMS
- DONE: Restarted bridge, account now loaded
- TODO: Remove Gmail credentials from approval_lane.json
- TODO: Update approvals.py to use Proton Bridge SMTP
- TODO: Build IMAP-to-OpenClaw-hook adapter for receiving email
- TODO: Add Proton hook mapping to OpenClaw gateway config
- OPTIONAL: Generate Proton SMTP Submission token as fallback
- OPTIONAL: Add systemd timer for bridge keychain race condition

5. WHY PROTON MAIL BRIDGE IS BEST
- Trusted: Official Proton AG, GPL-3.0, v3.25.0
- Secure: E2E encryption maintained, all crypto local
- Standard: IMAP + SMTP work with any library
- No cloud dependency: No third-party sees credentials
- Already deployed: Running on this machine
- OpenClaw compatible: Simple adapter feeds into hooks system
"""

html = """\
<html><body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; color: #333;">

<h1 style="color: #6d4aff; border-bottom: 2px solid #6d4aff; padding-bottom: 10px;">Proton Mail Integration Research Report</h1>
<h2 style="color: #555;">Kilo Substrate &amp; OpenClaw — August 13, 2026</h2>

<h3 style="color: #6d4aff;">Executive Summary</h3>
<p>After deep research into Proton Mail's integration surfaces, current infrastructure status, and security validation, here are the findings and recommended path forward.</p>

<h3 style="color: #6d4aff;">1. Integration Options Evaluated</h3>

<table style="border-collapse: collapse; width: 100%;">
<tr style="background: #6d4aff; color: white;">
  <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Option</th>
  <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Type</th>
  <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Status</th>
  <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Security</th>
  <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Verdict</th>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;"><b>Proton Mail Bridge</b> (IMAP/SMTP)</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Local relay</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Running v3.25.0<br>IMAP :1143, SMTP :1025</td>
  <td style="padding: 8px; border: 1px solid #ddd;">End-to-end encryption maintained. Bridge decrypts/encrypts locally. Ports bound to 127.0.0.1 only.</td>
  <td style="padding: 8px; border: 1px solid #ddd;"><b>RECOMMENDED</b></td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;"><b>Proton SMTP Submission</b> (smtp.ch:587)</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Remote SMTP relay</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Available (paid plan + custom domain)</td>
  <td style="padding: 8px; border: 1px solid #ddd;">STARTTLS, token-based auth (separate from login/mailbox password). Sent emails appear in Sent folder. <b>Not end-to-end encrypted.</b></td>
  <td style="padding: 8px; border: 1px solid #ddd;">Good for outbound only, no receive path</td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;"><b>Proton Mail API</b></td>
  <td style="padding: 8px; border: 1px solid #ddd;">REST API</td>
  <td style="padding: 8px; border: 1px solid #ddd;">No public general-purpose API exists</td>
  <td style="padding: 8px; border: 1px solid #ddd;">N/A</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Not available</td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;"><b>OpenClaw Hooks (Gmail-style)</b></td>
  <td style="padding: 8px; border: 1px solid #ddd;">Webhook + Pub/Sub</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Gmail preset exists; no Proton preset</td>
  <td style="padding: 8px; border: 1px solid #ddd;">OpenClaw has strong hook security (token auth, untrusted content wrapping, prompt injection protection)</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Could build a custom bridge-to-hook adapter</td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;"><b>Third-party IMAP pollers</b> (getmail, fetchmail)</td>
  <td style="padding: 8px; border: 1px solid #ddd;">IMAP polling</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Works with Bridge IMAP</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Local only, no cloud exposure</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Add-on for receive path</td>
</tr>
</table>

<h3 style="color: #6d4aff;">2. Current Infrastructure Status (FIXED THIS SESSION)</h3>
<p><b>Issue found:</b> The Proton Mail Bridge was running but had <b>zero accounts loaded</b> due to a keychain initialization failure at boot time. The gnome-keyring-daemon wasn't ready when the bridge started, causing it to fall back to insecure mode with no account decryption capability.</p>
<p><b>Fix applied:</b> Restarted the bridge service after confirming gnome-keyring was running and unlocked. The account is now loaded successfully:</p>
<ul>
<li>Keychain: SecretService (working, login collection unlocked)</li>
<li>Vault: Encrypted, 1 account loaded</li>
<li>SMTP: 127.0.0.1:1025 (STARTTLS, accepting connections)</li>
<li>IMAP: 127.0.0.1:1143 (STARTTLS, AUTH=PLAIN, IDLE capable)</li>
</ul>

<h3 style="color: #6d4aff;">3. Recommended Architecture</h3>

<h4 style="color: #555;">Send (Outbound Email)</h4>
<p><b>Primary:</b> Proton Mail Bridge SMTP (127.0.0.1:1025 with STARTTLS)</p>
<ul>
<li>Already integrated in the substrate approval lane (<code>substrate/approvals.py</code>)</li>
<li>Maintains end-to-end encryption through Bridge</li>
<li>Auth: Bridge uses its internal credentials (stored in encrypted vault)</li>
<li>Ports bound to localhost — no network exposure</li>
</ul>
<p><b>Fallback:</b> Proton SMTP Submission (smtp.ch:587, STARTTLS) — requires generating an SMTP token in Proton Settings. Good for when Bridge is unavailable, but sends are not E2E encrypted.</p>

<h4 style="color: #555;">Receive (Inbound Email)</h4>
<p><b>Primary:</b> Proton Mail Bridge IMAP (127.0.0.1:1143 with STARTTLS)</p>
<ul>
<li>Use IMAP IDLE for push notifications (Bridge supports IDLE capability)</li>
<li>Or poll IMAP for new messages on a schedule</li>
<li>Existing <code>substrate/approvals.py</code> already has IMAP reply-polling code</li>
</ul>

<h4 style="color: #555;">OpenClaw Integration</h4>
<p>OpenClaw has a robust <b>hooks system</b> that can receive inbound email via webhook. The built-in Gmail preset uses Google Pub/Sub to webhook, but a Proton equivalent can be built:</p>
<ol>
<li><b>IMAP-to-Hook bridge script:</b> A lightweight Python daemon that polls Bridge IMAP for new messages and POSTs them to <code>http://127.0.0.1:18789/hooks/proton</code> with the hook token</li>
<li><b>Custom hook mapping:</b> Add a <code>proton</code> path mapping in OpenClaw hooks config, with a transform module to parse the email payload</li>
<li><b>Session routing:</b> <code>sessionKey: "hook:proton:{{message_id}}"</code> for per-thread sessions</li>
<li><b>Outbound:</b> Use the substrate approval lane's SMTP code or a simple <code>sendmail</code> via Bridge SMTP</li>
</ol>

<h3 style="color: #6d4aff;">4. Security Validation</h3>

<table style="border-collapse: collapse; width: 100%;">
<tr style="background: #28a745; color: white;">
  <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Check</th>
  <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Result</th>
  <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Notes</th>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;">Bridge ports bound to localhost</td>
  <td style="padding: 8px; border: 1px solid #ddd;">PASS</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Both 1025 and 1143 bind 127.0.0.1 only — not exposed externally</td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;">Bridge vault encryption</td>
  <td style="padding: 8px; border: 1px solid #ddd;">PASS</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Vault encrypted via SecretService keychain; insecure=false after restart</td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;">STARTTLS on SMTP and IMAP</td>
  <td style="padding: 8px; border: 1px solid #ddd;">PASS</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Both services offer STARTTLS; connections upgrade to TLS</td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;">Keychain (secret-service) functional</td>
  <td style="padding: 8px; border: 1px solid #ddd;">PASS</td>
  <td style="padding: 8px; border: 1px solid #ddd;">gnome-keyring-daemon running, login collection unlocked, SecretService usable</td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;">Bridge account loaded</td>
  <td style="padding: 8px; border: 1px solid #ddd;">PASS</td>
  <td style="padding: 8px; border: 1px solid #ddd;">1 user loaded after restart; IMAP and SMTP accepting auth</td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;">No credentials in plaintext config</td>
  <td style="padding: 8px; border: 1px solid #ddd;">WARNING</td>
  <td style="padding: 8px; border: 1px solid #ddd;">The approval_lane.json config at ~/.config/substrate/ contains Gmail SMTP credentials in plaintext. <b>Recommend:</b> Remove Gmail SMTP config and use Proton Bridge SMTP only. Delete the <code>imap</code> and <code>smtp</code> sections with Gmail credentials.</td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;">OpenClaw hook token security</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Ready</td>
  <td style="padding: 8px; border: 1px solid #ddd;">OpenClaw hooks require bearer token auth; content is wrapped as untrusted (prompt injection protection). Keep <code>allowUnsafeExternalContent=false</code></td>
</tr>
<tr>
  <td style="padding: 8px; border: 1px solid #ddd;">Firewall</td>
  <td style="padding: 8px; border: 1px solid #ddd;">PASS</td>
  <td style="padding: 8px; border: 1px solid #ddd;">Bridge ports not exposed beyond localhost</td>
</tr>
</table>

<h3 style="color: #6d4aff;">5. Action Items</h3>
<ol>
<li><b>DONE:</b> Restarted Proton Bridge — account now loaded and syncing</li>
<li><b>TODO:</b> Remove Gmail credentials from <code>~/.config/substrate/approval_lane.json</code> — replace SMTP/IMAP config with Proton Bridge settings (127.0.0.1:1025 / 127.0.0.1:1143)</li>
<li><b>TODO:</b> Update <code>substrate/approvals.py</code> to use Proton Bridge SMTP for sending (remove Gmail SMTP fallback)</li>
<li><b>TODO:</b> Build IMAP-to-OpenClaw-hook adapter for receiving email (lightweight Python daemon or systemd service that polls Bridge IMAP then POSTs to OpenClaw hooks endpoint)</li>
<li><b>TODO:</b> Add Proton hook mapping to OpenClaw gateway config</li>
<li><b>OPTIONAL:</b> Generate Proton SMTP Submission token (smtp.ch:587) as a fallback for when Bridge is down — store in keyring, not plaintext</li>
<li><b>OPTIONAL:</b> Add a systemd timer to auto-restart the bridge if the keychain isn't ready (race condition fix)</li>
</ol>

<h3 style="color: #6d4aff;">6. Why Proton Mail Bridge is the Best Choice</h3>
<ul>
<li><b>Trusted:</b> Official Proton AG software, GPL-3.0, actively maintained (v3.25.0)</li>
<li><b>Secure:</b> Maintains end-to-end encryption; all crypto happens locally</li>
<li><b>Standard protocols:</b> IMAP + SMTP — works with any mail library or tool</li>
<li><b>No cloud API dependency:</b> No third-party service sees your credentials or mail</li>
<li><b>Already deployed:</b> Running on this machine, integrated into the substrate's approval lane code</li>
<li><b>OpenClaw compatible:</b> Can feed into OpenClaw's hook system via a simple adapter</li>
</ul>

<hr style="border: 1px solid #eee; margin: 20px 0;">
<p style="color: #888; font-size: 0.9em;">This report was generated by the Kilo agent substrate. Research sources: Proton official docs (proton.me/support), Proton Bridge GitHub (github.com/ProtonMail/proton-bridge), OpenClaw docs (local), substrate integrations.yaml, and live system inspection.</p>

</body></html>
"""

msg.attach(MIMEText(text, "plain"))
msg.attach(MIMEText(html, "html"))

# Send via Bridge SMTP with authentication
bridge_password = "Zps-aYFIKXec4qTrI1oVGA"

try:
    s = smtplib.SMTP("127.0.0.1", 1025, timeout=30)
    s.starttls()
    s.ehlo()
    s.login("ahronzombi@protonmail.com", bridge_password)
    s.sendmail("ahronzombi@protonmail.com", ["ahronzombi@protonmail.com"], msg.as_string())
    s.quit()
    print("Email sent successfully via Proton Mail Bridge SMTP!")
except Exception as e:
    print(f"Send error: {e}")
