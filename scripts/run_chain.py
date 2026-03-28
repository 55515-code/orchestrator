#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

import yaml
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from rich.console import Console


class ChainState(TypedDict, total=False):
    objective: str
    context: str
    outputs: dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a prompt chain from YAML config.")
    parser.add_argument(
        "--chain",
        default="chains/local-agent-chain.yaml",
        help="Path to chain YAML configuration.",
    )
    parser.add_argument(
        "--objective", required=True, help="Primary objective for the run."
    )
    parser.add_argument(
        "--context-file",
        action="append",
        default=[],
        help="Additional markdown/text context files to include.",
    )
    parser.add_argument(
        "--provider",
        choices=["local", "anthropic", "ollama", "mock"],
        help="LLM provider override.",
    )
    parser.add_argument("--model", help="Model override.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render prompts and skip provider calls.",
    )
    return parser.parse_args()


def load_chain_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Chain config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or "steps" not in data:
        raise ValueError("Chain config must be a mapping with a 'steps' list.")
    return data


def read_context(paths: list[str]) -> str:
    chunks: list[str] = []
    for raw_path in paths:
        file_path = Path(raw_path)
        if not file_path.exists():
            continue
        text = file_path.read_text(encoding="utf-8")
        chunks.append(f"## {file_path}\n\n{text}")
    return "\n\n".join(chunks).strip()


def build_model(provider: str, model: str):
    if provider == "local":
        pass  # using local router

        return None  # delegated to local roo-router
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=0)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, temperature=0)
    if provider == "mock":
        return None
    raise ValueError(f"Unsupported provider: {provider}")


def render_prompt(template_path: Path, state: ChainState) -> str:
    prompt_template = ChatPromptTemplate.from_template(
        template_path.read_text(encoding="utf-8")
    )
    outputs = state.get("outputs", {})
    previous_outputs = "\n\n".join(
        f"### {step_id}\n{content}" for step_id, content in outputs.items()
    ).strip()
    return prompt_template.format(
        objective=state.get("objective", ""),
        context=state.get("context", ""),
        previous_outputs=previous_outputs or "(none yet)",
        outputs_json=json.dumps(outputs, indent=2, ensure_ascii=False),
    )


def make_step_node(
    step: dict[str, Any],
    run_dir: Path,
    provider: str,
    model_name: str,
    dry_run: bool,
):
    step_id = step["id"]
    prompt_path = Path(step["prompt"])

    def _node(state: ChainState) -> ChainState:
        rendered_prompt = render_prompt(prompt_path, state)
        if dry_run or provider == "mock":
            response = (
                f"# Mock Response: {step_id}\n\n"
                f"Provider: `{provider}`\n"
                f"Model: `{model_name}`\n\n"
                "Rendered prompt preview:\n\n"
                f"{rendered_prompt[:4000]}"
            )
        else:
            model = build_model(provider, model_name)
            message = model.invoke(rendered_prompt)
            if isinstance(message.content, str):
                response = message.content
            else:
                response = json.dumps(message.content, indent=2, ensure_ascii=False)

        output_path = run_dir / f"{step.get('order', 0):02d}_{step_id}.md"
        output_path.write_text(response, encoding="utf-8")

        outputs = dict(state.get("outputs", {}))
        outputs[step_id] = response
        return {"outputs": outputs}

    return _node


def resolve_provider_and_model(
    cfg: dict[str, Any], provider_arg: str | None, model_arg: str | None
) -> tuple[str, str]:
    defaults = cfg.get("defaults", {})
    models = defaults.get("models", {})
    provider = provider_arg or defaults.get("provider", "mock")
    model = model_arg or models.get(provider, "mock-model")
    return provider, model


def run_chain(
    cfg: dict[str, Any],
    objective: str,
    context: str,
    provider: str,
    model: str,
    dry_run: bool,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = Path("memory") / "runs" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    steps = cfg["steps"]
    for index, step in enumerate(steps, start=1):
        step.setdefault("order", index)
        if "id" not in step or "prompt" not in step:
            raise ValueError("Each step must include 'id' and 'prompt'.")

    graph = StateGraph(ChainState)
    previous = START
    for step in steps:
        step_id = step["id"]
        graph.add_node(step_id, make_step_node(step, run_dir, provider, model, dry_run))
        graph.add_edge(previous, step_id)
        previous = step_id
    graph.add_edge(previous, END)

    workflow = graph.compile()
    final_state = workflow.invoke(
        {
            "objective": objective,
            "context": context,
            "outputs": {},
        }
    )

    summary = {
        "chain": cfg.get("name", "unnamed-chain"),
        "description": cfg.get("description", ""),
        "provider": provider,
        "model": model,
        "dry_run": dry_run,
        "objective": objective,
        "steps": [step["id"] for step in steps],
        "output_files": [f"{step['order']:02d}_{step['id']}.md" for step in steps],
        "final_output_step": steps[-1]["id"],
        "final_output_preview": final_state.get("outputs", {}).get(steps[-1]["id"], "")[
            :800
        ],
    }
    (run_dir / "run.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return run_dir


def main() -> int:
    load_dotenv()
    args = parse_args()
    console = Console()

    cfg = load_chain_config(Path(args.chain))
    cfg_context_files = [str(p) for p in cfg.get("context_files", [])]
    context = read_context(cfg_context_files + args.context_file)

    provider, model = resolve_provider_and_model(cfg, args.provider, args.model)
    run_dir = run_chain(
        cfg=cfg,
        objective=args.objective,
        context=context,
        provider=provider,
        model=model,
        dry_run=args.dry_run,
    )

    console.print(
        f"[green]Chain run completed.[/green] Outputs saved to [bold]{run_dir}[/bold]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
