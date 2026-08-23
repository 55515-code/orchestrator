# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup: camera names and locations, SSH hosts and aliases, preferred TTS voices, speaker/room names, device nicknames, anything environment-specific.

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Android OpenClaw node

- Preferred node: `nothing-3a` (`a303aa5317ec48d38527a49eb3f2b99d269de1b6455b8164e2b468f1ef7dd55e`).
- Use it only when connected **and** `nodes status` shows the required command declared (not merely a capability label): Android/Termux-specific checks need `system.run`, mobile browser work needs `browser.proxy`, and bounded local inference needs a compatible model returned by discovery.
- Keep ordinary repository commands, scheduled agents, builds, and tests on the gateway unless the task specifically benefits from Android. Never assume the phone has the workspace or host dependencies.
- For shell work on Android, call exec explicitly with `host=node`; `tools.exec.node` pins that explicit route while `tools.exec.host=auto` preserves gateway fallback for regular work.
- Browser node routing is manual and pinned to this device; target the node explicitly. If it is offline or its browser proxy is unavailable, use the gateway browser instead.
- Do not route sensitive sensor, SMS, camera, screen-recording, or outbound actions to the phone without the normal permission and user-confirmation checks.
- Local inference is opportunistic only: run discovery first and fall back if no compatible Ollama model is advertised.
- Current verification (2026-08-23): the node is connected but its approved snapshot declares `commands: []`; do not dispatch automation to it until the phone restarts/re-registers and the refreshed pairing declares commands. Gateway fallback remains mandatory.

## Related

- [Agent workspace](/concepts/agent-workspace)
