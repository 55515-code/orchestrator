#!/usr/bin/env python3
"""Ollama vision helper: analyze or critique images with a local vision model.

Uses urllib (avoids argv limits with large base64 payloads).
"""
import base64, json, sys, argparse, urllib.request
from pathlib import Path

DEFAULT_MODEL = "qwen3.5:9b"
OLLAMA = "http://127.0.0.1:11434/api/generate"


def ask(image_path, prompt, model=DEFAULT_MODEL, max_tokens=2048, temperature=0.3):
    img_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }).encode()
    req = urllib.request.Request(
        OLLAMA, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        resp = json.loads(r.read().decode())
    text = resp.get("response", "").strip()
    thinking = resp.get("thinking", "").strip()
    return text, thinking


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("prompt_file", nargs="?", default=None,
                    help="file containing prompt; if omitted reads stdin")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--no-thinking", action="store_true")
    args = ap.parse_args()
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text()
    else:
        prompt = sys.stdin.read()
    text, thinking = ask(args.image, prompt, model=args.model, max_tokens=args.max_tokens)
    if thinking and not args.no_thinking:
        sys.stderr.write("=== thinking ===\n" + thinking + "\n=== /thinking ===\n")
    print(text)
