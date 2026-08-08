#!/usr/bin/env python3
"""Local Scribe-style writing assistant via Ollama (privacy-preserving).

Usage:
  python3 scribe.py draft "request a samples from a supplier"
  python3 scribe.py proofread --text "i want to order 5 units of the thing"
  python3 scribe.py shorten --text "..."
  python3 scribe.py formalize --text "..."
"""
import argparse, json, sys, urllib.request

OLLAMA = "http://127.0.0.1:11434"
MODEL = "llama3.1:8b"

PROMPTS = {
    "draft": "You are a privacy-first email writing assistant. Write a complete, professional email based on this brief. Plain text, no preamble, no subject line label:\n\n{brief}",
    "proofread": "Proofread the following text for grammar, spelling, and clarity. Return only the corrected text:\n\n{text}",
    "shorten": "Shorten the following text to be more concise while keeping all meaning. Return only the shorter version:\n\n{text}",
    "formalize": "Rewrite the following text in a more formal, professional tone. Return only the rewritten text:\n\n{text}",
}


def run(prompt: str, model: str = MODEL) -> str:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 800},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())["response"].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=list(PROMPTS))
    ap.add_argument("--text", default="")
    ap.add_argument("--brief", default="")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    selected_model = args.model
    if args.mode == "draft":
        if not args.brief:
            print("Error: --brief required for draft", file=sys.stderr)
            return 2
        prompt = PROMPTS["draft"].format(brief=args.brief)
    else:
        if not args.text:
            print(f"Error: --text required for {args.mode}", file=sys.stderr)
            return 2
        prompt = PROMPTS[args.mode].format(text=args.text)
    try:
        print(run(prompt, selected_model))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
