# OpenClaw Production Deployment Checklist

Generated: 2026-08-11

## Current State

- **OpenClaw Gateway**: installed, configured, systemd unit `openclaw-gateway.service`
- **Control UI**: served on `http://127.0.0.1:8090/` (OpenClaw Control)
- **Tailscale ingress**: `https://cachyos-x8664.tail0b124a.ts.net:10000` → OpenClaw
- **Legacy panel**: disabled (`substrate-panel.service` has `ExecStart=/bin/true`, no `WantedBy=default.target`)
- **Lister**: monitors `openclaw-gateway.service` (port 8090) every 60s
- **Agency bootstrap**: `ensure_agency.py` manages `openclaw-gateway.service`

## Operator Commands (run these in order)

### 1. Disable legacy panel permanently (if not already)
```bash
systemctl --user disable --now substrate-panel.service
```

### 2. Restart OpenClaw gateway to pick up new config
```bash
systemctl --user restart openclaw-gateway.service
sleep 4
systemctl --user is-active openclaw-gateway.service
```

### 3. Verify port 8090 is bound to OpenClaw (node), not python
```bash
ss -tlnp | grep 8090
# Expected: node-MainThread (OpenClaw), NOT python3
```

### 4. Verify health endpoint
```bash
curl -s http://127.0.0.1:8090/health
# Expected: {"ok":true,"status":"live"}
```

### 5. Verify Tailscale ingress serves OpenClaw
```bash
curl -sk -o /dev/null -w '%{http_code}' https://cachyos-x8664.tail0b124a.ts.net:10000/
# Expected: 200
```

### 6. Make verification script executable and run it
```bash
chmod +x /home/ahron/codespace/scripts/verify_openclaw.sh
bash /home/ahron/codespace/scripts/verify_openclaw.sh
```

## Known Limitations

### Agent Context Overflow
OpenClaw's built-in agent runtime has a system prompt (~8K+ tokens) that exceeds the context window of local Ollama models (`llama3.1:8b`, `qwen2.5-coder:7b`). This causes agent execution to fail with `context_overflow` before any reply is generated.

**Workarounds (pick one):**

1. **Use Kilo CLI directly** (recommended):
   ```bash
   kilo run "your prompt here"
   ```
   Kilo routes through cloud models with large context (Kilo Gateway OAuth already configured).

2. **Configure Ollama Cloud auth** for `deepseek-v4-flash:cloud` (1M context):
   ```bash
   export OLLAMA_API_KEY="your-ollama-cloud-key"
   # Then set in openclaw.json or systemd service
   ```

3. **Add a cloud provider API key** to OpenClaw config:
   ```bash
   openclaw config set models.providers.openai.apiKey '"sk-..."' --strict-json
   openclaw config set agents.defaults.model '"openai/gpt-4o"' --strict-json
   ```

4. **Use the Kilo-runner skill** (`~/.openclaw/skills/kilo-runner/SKILL.md`):
   - Instructs OpenClaw agents to delegate AI tasks to `kilo run`
   - Requires the agent runtime to start first (blocked by context overflow)

### Legacy Panel Code
The legacy panel code (`substrate/web.py`, `substrate/iphone_panel.py`, `substrate/static/control-panel.*`) still exists on disk but is **not loaded** by any active service. Do not run `substrate.cli serve` as it will conflict with OpenClaw on port 8090.

## Files Modified in This Session

| File | Change |
|------|--------|
| `~/.openclaw/openclaw.json` | Default model → `ollama/llama3.1:8b`, minimal tools, skill limits |
| `~/.config/systemd/user/substrate-panel.service` | ExecStart=/bin/true, no auto-start |
| `~/.openclaw/skills/kilo-runner/SKILL.md` | Created Kilo CLI delegation skill |
| `scripts/verify_openclaw.sh` | Created verification script |
| `scripts/substrate_lister.py` | Monitors openclaw-gateway.service |
| `scripts/ensure_agency.py` | Manages openclaw-gateway.service |
| `scripts/monitor_panel.sh` | Points to openclaw-gateway.service |
| `substrate/iphone_panel.py` | Service list updated |
| `substrate/swarm_control.py` | SERVICE_NAME updated |

## Support

- OpenClaw docs: https://docs.openclaw.ai/cli
- OpenClaw gateway logs: `journalctl --user -u openclaw-gateway.service -f`
- Kilo CLI help: `kilo --help`
- Tailscale serve status: `tailscale serve status`
