from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .main import create_app
from .runtime_config import (
    DEFAULT_VERSION,
    RuntimeOptions,
    choose_free_port,
    detect_bundled_codex_executable,
    detect_runtime_root,
    normalize_channel,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Codex Scheduler Studio.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--desktop-mode", action="store_true")
    parser.add_argument("--data-dir")
    parser.add_argument("--channel", default="stable")
    parser.add_argument("--session-token")
    parser.add_argument("--update-base-url")
    parser.add_argument("--db-url")
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--disable-scheduler", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parent.parent
    runtime_root = detect_runtime_root(project_root)
    port = args.port
    if port == 0:
        port = choose_free_port(args.host)

    options = RuntimeOptions(
        mode="desktop" if args.desktop_mode else "server",
        channel=normalize_channel(args.channel),
        host=args.host,
        port=port,
        data_dir=Path(args.data_dir).resolve() if args.data_dir else None,
        session_token=args.session_token,
        bundled_codex_executable=detect_bundled_codex_executable(runtime_root),
        update_base_url=args.update_base_url,
        version=DEFAULT_VERSION,
    )
    app = create_app(
        start_scheduler=not args.disable_scheduler,
        db_url=args.db_url,
        runtime_options=options,
    )
    uvicorn.run(app, host=args.host, port=port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
