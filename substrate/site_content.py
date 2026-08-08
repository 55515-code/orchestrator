from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .registry import SubstrateRuntime

ALLOWED_KINDS = {"blog", "updates"}
SITE_REL = Path("ahrondarnell-site")
QUEUE_REL = Path("ahrondarnell-site/.content-queue")
STATE_REL = Path("state/content-queue.json")


def _runtime_site_root(runtime: SubstrateRuntime) -> Path:
    return (runtime.root / SITE_REL).resolve()


def _site_root_fallback() -> Path:
    candidate = (Path(__file__).resolve().parents[1] / SITE_REL).resolve()
    if candidate.exists():
        return candidate
    from .settings import discover_workspace_root

    return (discover_workspace_root() / SITE_REL).resolve()


def _slugify(text: str) -> str:
    value = text.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "untitled"


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _collection_dir(site_root: Path, kind: str) -> Path:
    return site_root / "src" / "content" / kind


def _queue_dirs(site_root: Path) -> dict[str, Path]:
    queue_root = site_root / ".content-queue"
    return {
        "root": queue_root,
        "inbox": queue_root / "inbox",
        "approved": queue_root / "approved",
        "rejected": queue_root / "rejected",
    }


def _ensure_dirs(site_root: Path) -> None:
    for kind in ALLOWED_KINDS:
        _collection_dir(site_root, kind).mkdir(parents=True, exist_ok=True)
    for d in _queue_dirs(site_root).values():
        d.mkdir(parents=True, exist_ok=True)


def _parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    try:
        import yaml

        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    return data, body


def validate_collection_file(path: Path, kind: str) -> list[str]:
    errors: list[str] = []
    data, body = _parse_frontmatter(path)
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    pub_date = data.get("pubDate") or data.get("pubDate".lower())
    tags = data.get("tags")
    draft = data.get("draft")

    if kind == "blog":
        if len(title) < 4 or len(title) > 120:
            errors.append("title must be 4-120 chars")
        if len(description) < 20 or len(description) > 300:
            errors.append("description must be 20-300 chars")
        if tags is not None and not isinstance(tags, list):
            errors.append("tags must be a list")
        if draft is not None and not isinstance(draft, bool):
            errors.append("draft must be boolean")
    if kind == "updates":
        if len(title) < 4 or len(title) > 120:
            errors.append("title must be 4-120 chars")
        if len(description) < 20 or len(description) > 300:
            errors.append("description must be 20-300 chars")
    if pub_date is None:
        errors.append("pubDate is required")
    else:
        try:
            datetime.fromisoformat(str(pub_date).replace("Z", "+00:00"))
        except Exception:
            try:
                datetime.strptime(str(pub_date), "%Y-%m-%d")
            except Exception:
                errors.append(f"pubDate is not a valid date: {pub_date}")
    if not body.strip():
        errors.append("body is empty")
    return errors


@dataclass
class NewPostResult:
    kind: str
    slug: str
    path: str
    already_existed: bool


def new_post(
    *,
    site_root: Path | None = None,
    kind: str = "blog",
    title: str,
    slug: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> NewPostResult:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"kind must be one of {sorted(ALLOWED_KINDS)}")
    if not title or not title.strip():
        raise ValueError("title is required")
    site_root = (site_root or _site_root_fallback()).resolve()
    _ensure_dirs(site_root)
    slug = _slugify(slug or title)
    if kind == "blog":
        target = _collection_dir(site_root, "blog") / f"{slug}.md"
    else:
        target = _collection_dir(site_root, "updates") / f"{_today_iso()}-{slug}.md"
    already = target.exists()
    if already:
        return NewPostResult(kind=kind, slug=slug, path=str(target), already_existed=True)
    desc = (description or f"Draft: {title}").strip()
    if len(desc) < 20:
        desc = (desc + " — more detail to come.").strip()
    today = _today_iso()
    if kind == "blog":
        tag_line = ""
        if tags:
            tag_str = ", ".join(f'"{t.strip()}"' for t in tags if t.strip())
            tag_line = f"\ntags: [{tag_str}]"
        content = f"""---
title: "{title.replace('"', '\\"')}"
description: "{desc.replace('"', '\\"')}"
pubDate: {today}
author: "Ahron Darnell"{tag_line}
draft: true
---

Write the post body here. Use markdown. Keep the intro answer-shaped (40-60 words) so AI crawlers can cite it.

## Why this matters

Explain the context in plain English.

## What to do next

- Step 1
- Step 2
- Step 3
"""
    else:
        content = f"""---
title: "{title.replace('"', '\\"')}"
description: "{desc.replace('"', '\\"')}"
pubDate: {today}
author: "Ahron Darnell"
draft: false
---

Short update body. One or two paragraphs.
"""
    target.write_text(content, encoding="utf-8")
    return NewPostResult(kind=kind, slug=slug, path=str(target), already_existed=False)


def list_posts(*, site_root: Path | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    site_root = (site_root or _site_root_fallback()).resolve()
    kinds = [kind] if kind in ALLOWED_KINDS else sorted(ALLOWED_KINDS)
    rows: list[dict[str, Any]] = []
    for k in kinds:
        d = _collection_dir(site_root, k)
        if not d.exists():
            continue
        for path in sorted(d.glob("*.md")):
            data, _ = _parse_frontmatter(path)
            rows.append(
                {
                    "kind": k,
                    "slug": path.stem,
                    "path": str(path.relative_to(site_root)),
                    "title": str(data.get("title") or ""),
                    "draft": bool(data.get("draft", False)),
                    "pubDate": str(data.get("pubDate") or ""),
                }
            )
    rows.sort(key=lambda r: (r["kind"], r["slug"]))
    return rows


def validate_posts(*, site_root: Path | None = None, kind: str | None = None) -> dict[str, Any]:
    site_root = (site_root or _site_root_fallback()).resolve()
    kinds = [kind] if kind in ALLOWED_KINDS else sorted(ALLOWED_KINDS)
    files: list[Path] = []
    for k in kinds:
        d = _collection_dir(site_root, k)
        if d.exists():
            files.extend(sorted(d.glob("*.md")))
    results: list[dict[str, Any]] = []
    failed = 0
    for path in files:
        sub_kind = "blog" if "src/content/blog" in str(path) else "updates"
        errs = validate_collection_file(path, sub_kind)
        if errs:
            failed += 1
        results.append(
            {
                "path": str(path.relative_to(site_root)),
                "kind": sub_kind,
                "ok": not errs,
                "errors": errs,
            }
        )
    return {"total": len(results), "failed": failed, "passed": len(results) - failed, "results": results}


def build_site(*, site_root: Path | None = None) -> dict[str, Any]:
    site_root = (site_root or _site_root_fallback()).resolve()
    cmd = ["npm", "run", "build"]
    completed = subprocess.run(cmd, cwd=site_root, capture_output=True, text=True, check=False)
    return {
        "command": " ".join(cmd),
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_tail": completed.stdout[-3000:],
        "stderr_tail": completed.stderr[-3000:],
    }


def site_check(*, site_root: Path | None = None) -> dict[str, Any]:
    site_root = (site_root or _site_root_fallback()).resolve()
    cmd = ["npm", "run", "check"]
    completed = subprocess.run(cmd, cwd=site_root, capture_output=True, text=True, check=False)
    return {
        "command": " ".join(cmd),
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_tail": completed.stdout[-3000:],
        "stderr_tail": completed.stderr[-3000:],
    }


def _queue_state_path(runtime: SubstrateRuntime | None = None) -> Path:
    if runtime is not None:
        return runtime.paths["state"] / "content-queue.json"
    from .settings import discover_workspace_root, workspace_paths

    root = discover_workspace_root()
    return workspace_paths(root)["state"] / "content-queue.json"


def _read_queue_state(runtime: SubstrateRuntime | None = None) -> dict[str, Any]:
    path = _queue_state_path(runtime)
    if not path.exists():
        return {"inbox": [], "approved": [], "rejected": [], "history": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
        if not isinstance(payload, dict):
            return {"inbox": [], "approved": [], "rejected": [], "history": []}
        return payload
    except Exception:
        return {"inbox": [], "approved": [], "rejected": [], "history": []}


def _write_queue_state(state: dict[str, Any], runtime: SubstrateRuntime | None = None) -> None:
    path = _queue_state_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def queue_list(*, site_root: Path | None = None, runtime: SubstrateRuntime | None = None) -> dict[str, Any]:
    site_root = (site_root or _site_root_fallback()).resolve()
    _ensure_dirs(site_root)
    dirs = _queue_dirs(site_root)
    inbox_files = sorted(dirs["inbox"].glob("*.md"))
    rows: list[dict[str, Any]] = []
    for path in inbox_files:
        data, _ = _parse_frontmatter(path)
        errs = validate_collection_file(path, "blog")
        rows.append(
            {
                "file": path.name,
                "path": str(path.relative_to(site_root)),
                "title": str(data.get("title") or ""),
                "pubDate": str(data.get("pubDate") or ""),
                "ok": not errs,
                "errors": errs,
            }
        )
    return {"count": len(rows), "items": rows, "dirs": {k: str(v) for k, v in dirs.items()}}


def queue_submit(
    *,
    site_root: Path | None = None,
    source_path: str,
    target_name: str | None = None,
) -> dict[str, Any]:
    site_root = (site_root or _site_root_fallback()).resolve()
    _ensure_dirs(site_root)
    src = Path(source_path).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"source not found: {source_path}")
    dirs = _queue_dirs(site_root)
    dest_name = target_name or src.name
    if not dest_name.endswith(".md"):
        dest_name += ".md"
    dest = dirs["inbox"] / dest_name
    if dest.exists():
        raise FileExistsError(f"queue inbox already contains: {dest_name}")
    shutil.copy2(src, dest)
    errs = validate_collection_file(dest, "blog")
    return {"file": dest.name, "path": str(dest.relative_to(site_root)), "ok": not errs, "errors": errs}


def _move_queue_file(site_root: Path, filename: str, dest_key: str) -> Path:
    dirs = _queue_dirs(site_root)
    src = dirs["inbox"] / filename
    if not src.exists():
        raise FileNotFoundError(f"not in inbox: {filename}")
    dest_dir = dirs[dest_key]
    dest = dest_dir / filename
    shutil.move(str(src), str(dest))
    return dest


def queue_approve(
    *,
    site_root: Path | None = None,
    runtime: SubstrateRuntime | None = None,
    filename: str,
    kind: str = "blog",
    slug: str | None = None,
) -> dict[str, Any]:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"kind must be one of {sorted(ALLOWED_KINDS)}")
    site_root = (site_root or _site_root_fallback()).resolve()
    _ensure_dirs(site_root)
    dirs = _queue_dirs(site_root)
    src = dirs["inbox"] / filename
    if not src.exists():
        raise FileNotFoundError(f"not in inbox: {filename}")
    errs = validate_collection_file(src, kind)
    if errs:
        raise ValueError(f"cannot approve: validation failed: {errs}")
    resolved_slug = _slugify(slug or src.stem)
    target = _collection_dir(site_root, kind) / f"{resolved_slug}.md"
    if kind == "updates":
        target = _collection_dir(site_root, kind) / f"{_today_iso()}-{resolved_slug}.md"
    if target.exists():
        raise FileExistsError(f"target already exists: {target.name}")
    data, _ = _parse_frontmatter(src)
    if data.get("draft") is True:
        text = src.read_text(encoding="utf-8")
        text = text.replace("draft: true", "draft: false", 1)
        src.write_text(text, encoding="utf-8")
    shutil.move(str(src), str(target))
    state = _read_queue_state(runtime)
    state.setdefault("history", []).append(
        {
            "action": "approve",
            "file": filename,
            "kind": kind,
            "slug": resolved_slug,
            "target": str(target.relative_to(site_root)),
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_queue_state(state, runtime)
    return {"approved": True, "target": str(target.relative_to(site_root)), "slug": resolved_slug}


def queue_reject(
    *,
    site_root: Path | None = None,
    runtime: SubstrateRuntime | None = None,
    filename: str,
    reason: str = "",
) -> dict[str, Any]:
    site_root = (site_root or _site_root_fallback()).resolve()
    _ensure_dirs(site_root)
    dest = _move_queue_file(site_root, filename, "rejected")
    state = _read_queue_state(runtime)
    state.setdefault("history", []).append(
        {
            "action": "reject",
            "file": filename,
            "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_queue_state(state, runtime)
    return {"rejected": True, "path": str(dest.relative_to(site_root))}


def queue_status(*, site_root: Path | None = None, runtime: SubstrateRuntime | None = None) -> dict[str, Any]:
    site_root = (site_root or _site_root_fallback()).resolve()
    _ensure_dirs(site_root)
    q = queue_list(site_root=site_root, runtime=runtime)
    v = validate_posts(site_root=site_root)
    state = _read_queue_state(runtime)
    return {
        "queue": q,
        "collection_validation": v,
        "history": state.get("history", [])[-20:],
    }


def cli_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="site_content", description="1pointo local site + moderation tooling")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="scaffold new post")
    p_new.add_argument("--kind", choices=sorted(ALLOWED_KINDS), default="blog")
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--slug", default="")
    p_new.add_argument("--description", default="")
    p_new.add_argument("--tags", default="", help="comma-separated")

    p_list = sub.add_parser("list", help="list collection posts")
    p_list.add_argument("--kind", choices=sorted(ALLOWED_KINDS))

    sub.add_parser("validate", help="validate collection frontmatter")
    sub.add_parser("build", help="npm run build")
    sub.add_parser("check", help="npm run check (astro check)")

    sub.add_parser("queue-list", help="list moderation inbox")
    p_submit = sub.add_parser("queue-submit", help="copy file into inbox")
    p_submit.add_argument("--source", required=True)
    p_submit.add_argument("--name", default="")

    p_approve = sub.add_parser("queue-approve", help="approve inbox file into collection")
    p_approve.add_argument("--file", required=True, help="filename in inbox")
    p_approve.add_argument("--kind", choices=sorted(ALLOWED_KINDS), default="blog")
    p_approve.add_argument("--slug", default="")

    p_reject = sub.add_parser("queue-reject", help="reject inbox file")
    p_reject.add_argument("--file", required=True)
    p_reject.add_argument("--reason", default="")

    sub.add_parser("queue-status", help="queue + validation summary")
    sub.add_parser("status", help="alias for queue-status")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "new":
            tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
            res = new_post(kind=args.kind, title=args.title, slug=args.slug or None, description=args.description or None, tags=tags)
            print(json.dumps({"kind": res.kind, "slug": res.slug, "path": res.path, "already_existed": res.already_existed}, indent=2))
        elif args.cmd == "list":
            print(json.dumps(list_posts(kind=args.kind), indent=2, ensure_ascii=False))
        elif args.cmd == "validate":
            payload = validate_posts()
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 1 if payload["failed"] else 0
        elif args.cmd == "build":
            print(json.dumps(build_site(), indent=2, ensure_ascii=False))
        elif args.cmd == "check":
            print(json.dumps(site_check(), indent=2, ensure_ascii=False))
        elif args.cmd == "queue-list":
            print(json.dumps(queue_list(), indent=2, ensure_ascii=False))
        elif args.cmd == "queue-submit":
            print(json.dumps(queue_submit(source_path=args.source, target_name=args.name or None), indent=2, ensure_ascii=False))
        elif args.cmd == "queue-approve":
            print(json.dumps(queue_approve(filename=args.file, kind=args.kind, slug=args.slug or None), indent=2, ensure_ascii=False))
        elif args.cmd == "queue-reject":
            print(json.dumps(queue_reject(filename=args.file, reason=args.reason), indent=2, ensure_ascii=False))
        elif args.cmd in {"queue-status", "status"}:
            print(json.dumps(queue_status(), indent=2, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
