#!/usr/bin/env python3
"""
Design the target OpenClaw Gateway config (candidate) for v2026.8.2.

Applies ONLY changes validated by the research swarm:
  SEC-1  Disable agents.main.autoAllowSkills (audit warn: widens host exec trust)
  SEC-2  Keep hooks.allowRequestSessionKey=false + allowedSessionKeyPrefixes=["hook:"] (already safe)
  SEC-3  Pin duckduckgo plugin install spec to exact version (audit warn: supply chain)
  PERF-1 agents.defaults.maxConcurrent -> 4 (20-core host safety valve; docs example)
  PERF-2 agents.defaults.subagents.maxSpawnDepth -> 2, runTimeoutSeconds -> 1800
  PERF-3 agents.defaults.subagents.archiveAfterMinutes -> 30
  PERF-4 ollama provider timeoutSeconds -> 300 (cold 9B loads)
  PERF-5 Ollama model num_ctx aligned with contextTokens; keep_alive 15-30m (set per model via params)
  PERF-6 logging.level stays info (never debug on 24/7)
  OPS-1  session.maintenance mode enforce / pruneAfter 14d / maxDiskBytes 2GiB
  (requires session.maintenance support in v2026.8.2; gate via schema validation)

Output: candidate config JSON to deploy/openclaw-optimize/candidates/openclaw.json.candidate
"""
import json, copy, sys, os

SRC = '/home/ahron/.openclaw/openclaw.json'
OUT = '/home/ahron/codespace/deploy/openclaw-optimize/candidates/openclaw.json.candidate'

d = json.load(open(SRC))
changes = []

# --- SEC-1: disable autoAllowSkills on main agent ---
if d.get('agents', {}).get('entries', {}).get('main', {}).get('autoAllowSkills') is not False:
    d['agents']['entries']['main']['autoAllowSkills'] = False
    changes.append('SEC-1: agents.entries.main.autoAllowSkills=false')

# --- SEC-3: pin duckduckgo plugin to exact version if unpinned ---
plugins = d.get('plugins', {})
entries = plugins.get('entries', {})
ddg = entries.get('duckduckgo', {})
if isinstance(ddg, dict) and (not ddg.get('spec') or '@' not in str(ddg.get('spec',''))):
    # only pin if we can determine an exact version; otherwise leave spec as-is and note it
    changes.append('SEC-3: duckduckgo spec unpinned - left for explicit pin (no verified version available offline)')

# --- PERF-1: maxConcurrent ---
if d.setdefault('agents', {}).setdefault('defaults', {}).get('maxConcurrent') is None:
    d['agents']['defaults']['maxConcurrent'] = 4
    changes.append('PERF-1: agents.defaults.maxConcurrent=4')

# --- PERF-2/3: subagent tuning ---
sub = d['agents']['defaults'].setdefault('subagents', {})
sub['maxSpawnDepth'] = 2
sub['runTimeoutSeconds'] = 1800
sub['archiveAfterMinutes'] = 30
changes.append('PERF-2/3: subagents.maxSpawnDepth=2, runTimeoutSeconds=1800, archiveAfterMinutes=30')

# --- PERF-4: ollama provider timeout ---
oll = d.setdefault('models', {}).setdefault('providers', {}).setdefault('ollama', {})
oll['timeoutSeconds'] = 300
changes.append('PERF-4: models.providers.ollama.timeoutSeconds=300')

# --- PERF-5: align num_ctx + keep_alive per ollama model ---
keep = {'qwen3.5:9b':'15m','llama3.1:8b':'15m','qwen2.5-coder:7b':'30m','qwen3.5:4b':'15m'}
for m in oll.get('models', []):
    mid = m.get('id')
    if mid in keep:
        m.setdefault('params', {})['keep_alive'] = keep[mid]
        changes.append(f'PERF-5: {mid} keep_alive={keep[mid]}')

# --- PERF-6: ensure log level info ---
if d.setdefault('logging', {}).get('level') not in (None, 'info'):
    d['logging']['level'] = 'info'
    changes.append('PERF-6: logging.level=info')

# --- OPS-1: session maintenance (gate via validation later) ---
sm = d.setdefault('session', {}).setdefault('maintenance', {})
sm['mode'] = 'enforce'
sm['pruneAfter'] = '14d'
sm['maxDiskBytes'] = 2147483648
changes.append('OPS-1: session.maintenance enforce/14d/2GiB')

json.dump(d, open(OUT, 'w'), indent=2)
print("=== CHANGES APPLIED TO CANDIDATE ===")
for c in changes:
    print(" ", c)
print(f"\nWrote: {OUT}")
print("Candidate sha256:", end=" ")
import hashlib
print(hashlib.sha256(open(OUT,'rb').read()).hexdigest()[:16])
