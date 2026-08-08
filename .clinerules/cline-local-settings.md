# Recommended Cline Local Settings

Use these settings for local Ollama work on this laptop.

## Provider

- API Provider: Ollama
- Base URL: http://127.0.0.1:11434
- Model: qwen2.5-coder:7b

## Model Settings

- Context window: 8192
- Max output tokens: 512 for planning, 1024 for small edits
- Temperature: 0.2
- Compact Prompt: ON
- Streaming: ON if available

## Safety Settings

- Plan mode first
- Auto-approve: OFF
- YOLO mode: OFF
- Browser actions: OFF unless explicitly needed
- MCP/tools/skills: OFF unless reviewed
- Do not commit
- Do not push
- Do not run package installs
- Do not run sudo/systemctl/gcloud/tailscale commands

## First Prompt Template

LOCAL PLAN MODE ONLY.

Read and follow:
- /home/ahron/codespace/*.md
- /home/ahron/codespace/README.md
- /home/ahron/codespace/*/*md
- AI_USAGE_RULES.md
- .clineignore
- .clinerules/local-agent-ops.md
- .clinerules/cline-local-settings.md

