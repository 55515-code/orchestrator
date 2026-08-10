"""Render orchestration router: local GPU engines + hosted API fallback."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from . import _utils
from .cache_store import CacheStore
from .registry import SubstrateRuntime
from .render_engines.base import (
    EngineSpec,
    RenderRequest,
    RenderUnavailable,
    detect_gpu,
    ensure_scratch_env,
    load_engine,
    QUALITY_TIERS,
    SPEED_TIERS,
)
from .reliability import ProviderFailoverHook


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def render_catalog_payload(runtime: SubstrateRuntime, engine_id: str | None = None) -> dict[str, Any]:
    source = _utils.load_yaml(runtime.paths["render_profiles"])
    gpu = detect_gpu()
    engines: list[dict[str, Any]] = []
    for raw in _utils.ensure_list(source.get("engines"), "engines"):
        try:
            spec = EngineSpec.from_mapping(raw)
        except ValueError as exc:
            engines.append({
                "id": raw.get("id", "<missing>"),
                "error": str(exc),
                "available": False,
                "available_reason": str(exc),
                "impl_loadable": False,
            })
            continue
        if engine_id is not None and spec.id != engine_id:
            continue
        impl_loadable = True
        available_reason = ""
        try:
            engine = load_engine(spec)
            ok, reason = engine.availability(gpu=gpu)
            available = ok
            available_reason = reason
        except Exception as exc:
            available = False
            available_reason = str(exc)
            impl_loadable = False
        engines.append({
            **spec.to_dict(),
            "available": available,
            "available_reason": available_reason,
            "impl_loadable": impl_loadable,
        })
    return {
        "version": int(source.get("version") or 1),
        "defaults": source.get("defaults", {}),
        "gpu": gpu,
        "engines": engines,
    }


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def select_engine(
    runtime: SubstrateRuntime,
    request: RenderRequest,
    optimize_for: str = "quality",
    forced_engine: str | None = None,
    dry_run: bool = False,
) -> EngineSpec:
    source = _utils.load_yaml(runtime.paths["render_profiles"])
    defaults = source.get("defaults", {})
    local_first: bool = bool(defaults.get("local_first", True))
    allow_hosted: bool = bool(defaults.get("allow_hosted", False))
    max_cost: float = float(defaults.get("max_cost_usd", 0.50))

    specs: dict[str, EngineSpec] = {}
    for raw in _utils.ensure_list(source.get("engines"), "engines"):
        try:
            spec = EngineSpec.from_mapping(raw)
        except ValueError:
            continue
        specs[spec.id] = spec

    if forced_engine is not None:
        spec = specs.get(forced_engine)
        if spec is None:
            raise ValueError(f"Unknown forced engine '{forced_engine}'.")
        if not spec.enabled:
            raise ValueError(f"Engine '{forced_engine}' is disabled in render_profiles.yaml.")
        return spec

    def _engine_ok(spec: EngineSpec) -> bool:
        if not spec.enabled:
            return False
        if not spec.supports("text_to_image") and not spec.supports(request.mode):
            return False
        if spec.kind == "hosted_api" and not allow_hosted:
            return False
        if spec.cost_per_image_usd * request.num_images > max_cost:
            return False
        return True

    def _rank(spec: EngineSpec) -> tuple[int, int, float]:
        q = QUALITY_TIERS.index(spec.quality_tier) if spec.quality_tier in QUALITY_TIERS else -1
        s = SPEED_TIERS.index(spec.speed_tier) if spec.speed_tier in SPEED_TIERS else -1
        cost = spec.cost_per_image_usd
        if optimize_for == "quality":
            return (-q, -s, cost)
        if optimize_for == "speed":
            return (s, -q, cost)
        if optimize_for == "cost":
            return (int(cost * 1e6), -q, -s)
        return (-q, -s, cost)

    candidates = [spec for spec in specs.values() if _engine_ok(spec)]
    candidates.sort(key=_rank)

    if local_first:
        locals_ = [s for s in candidates if s.kind == "local_gpu"]
        hosted_ = [s for s in candidates if s.kind == "hosted_api"]
        ordered = locals_ + hosted_
    else:
        ordered = candidates

    if dry_run:
        return ordered[0] if ordered else _raise_no_engine()

    gpu = detect_gpu()
    hook = ProviderFailoverHook(
        fallback_order=[s.id for s in ordered],
        provider_models={s.id: s.model_id for s in ordered},
    )

    current = None
    attempt = 0
    while True:
        for spec in ordered:
            if not hook.is_provider_healthy(spec.id):
                continue
            try:
                engine = load_engine(spec)
                ok, reason = engine.availability(gpu=gpu)
                if ok:
                    return spec
            except Exception:
                hook.mark_provider_unhealthy(spec.id)
        if current is None:
            break
        attempt += 1
        nxt = hook.next_target(
            run_id="select",
            step_id=None,
            attempt=attempt,
            current=type("T", (), {"provider": current.id, "model": current.model_id})(),
            failure=type("F", (), {"kind": "transient"})(),
            error=RuntimeError("unavailable"),
        )
        if nxt is None:
            break
        current = specs.get(nxt.provider)

    raise RenderUnavailable("no render engine available: all candidates unavailable or disabled.")


def _raise_no_engine() -> EngineSpec:
    raise RenderUnavailable("no render engine available: no engine matches the request constraints.")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def render_dispatch(
    runtime: SubstrateRuntime,
    request: RenderRequest,
    optimize_for: str = "quality",
    forced_engine: str | None = None,
    use_cache: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    request.validate()
    ensure_scratch_env(runtime.root)

    if dry_run:
        spec = select_engine(runtime, request, optimize_for, forced_engine, dry_run=True)
        gpu = detect_gpu()
        return {
            "status": "dry_run",
            "engine": spec.to_dict(),
            "request": request.to_dict(),
            "gpu": gpu,
        }

    gpu = detect_gpu()
    spec = select_engine(runtime, request, optimize_for, forced_engine)
    engine = load_engine(spec)
    engine.require_available(gpu=gpu)

    cache_key = None
    if use_cache:
        cache_key = _render_cache_key(spec, request)
        store = CacheStore(runtime.paths["render_cache"])
        cached = store.get(cache_key)
        if cached is not None:
            return {**cached, "cache_hit": True}

    t0 = time.monotonic()
    result = engine.render(request)
    latency_ms = int((time.monotonic() - t0) * 1000)
    if result.latency_ms == 0:
        result.latency_ms = latency_ms

    run_type = "render"
    if result.status == "success":
        try:
            from .learning import record_execution  # noqa: PLC0415
            record_execution(
                runtime,
                run_type=run_type,
                status="success",
                exit_code=0,
                stdout=json_dumps(result.to_dict()),
                note=f"render {spec.id}",
            )
        except Exception:
            pass
        try:
            runtime.db.record_render_event(
                engine_id=spec.id,
                kind=spec.kind,
                status="success",
                model_id=spec.model_id,
                mode=request.mode,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
                quality_score=result.quality_score,
                width=request.width,
                height=request.height,
                steps=request.steps,
                seed=request.seed,
                output_paths=[str(p) for p in result.images],
                metadata=result.metadata,
            )
        except Exception:
            pass
        if use_cache and cache_key:
            try:
                store = CacheStore(runtime.paths["render_cache"])
                store.set(cache_key, result.to_dict(), kind="render", summary=f"{spec.id} {request.prompt[:80]}")
            except Exception:
                pass
        return {**result.to_dict(), "cache_hit": False}

    failed = result
    try:
        from .learning import record_execution  # noqa: PLC0415
        record_execution(
            runtime,
            run_type=run_type,
            status="failed",
            exit_code=1,
            stderr=result.error or "",
            note=f"render {spec.id} failed",
        )
    except Exception:
        pass
    try:
        runtime.db.record_render_event(
            engine_id=spec.id,
            kind=spec.kind,
            status="failed",
            model_id=spec.model_id,
            mode=request.mode,
            latency_ms=result.latency_ms,
            error_text=result.error,
            metadata=result.metadata,
        )
    except Exception:
        pass
    return {**failed.to_dict(), "cache_hit": False}


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


def render_telemetry_payload(runtime: SubstrateRuntime) -> dict[str, Any]:
    return {
        "leaderboard": runtime.db.engine_leaderboard(limit_per_engine=50),
        "spend": runtime.db.render_spend(),
        "recent": runtime.db.recent_render_events(limit=25),
    }


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def _render_cache_key(spec: EngineSpec, request: RenderRequest) -> str:
    payload = {
        "engine_id": spec.id,
        "model_id": spec.model_id,
        "prompt": request.prompt,
        "negative": request.negative,
        "width": request.width,
        "height": request.height,
        "steps": request.steps,
        "guidance": request.guidance,
        "seed": request.seed,
        "num_images": request.num_images,
        "mode": request.mode,
        "source_image": str(request.source_image) if request.source_image else None,
        "style_refs": [str(p) for p in request.style_refs],
    }
    canonical = json_dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def json_dumps(payload: Any, **kwargs: Any) -> str:
    import json  # noqa: PLC0415
    return json.dumps(payload, **kwargs)


# ---------------------------------------------------------------------------
# CLI wiring (add to substrate/cli.py)
# ---------------------------------------------------------------------------

"""
# Add near the other subparser blocks in _build_parser():
render_catalog_p = subparsers.add_parser("render-catalog", help="Render engine catalog.")
render_catalog_p.add_argument("--engine", help="Filter to one engine id.")

render_run_p = subparsers.add_parser("render-run", help="Dispatch a render job.")
render_run_p.add_argument("--prompt", required=True)
render_run_p.add_argument("--negative", default="")
render_run_p.add_argument("--width", type=int, default=1024)
render_run_p.add_argument("--height", type=int, default=1024)
render_run_p.add_argument("--engine", help="Force a specific engine id.")
render_run_p.add_argument("--optimize-for", choices=["quality", "speed", "cost"], default="quality")
render_run_p.add_argument("--output", help="Output path (workspace-relative or absolute).")
render_run_p.add_argument("--no-cache", action="store_true")
render_run_p.add_argument("--dry-run", action="store_true")

subparsers.add_parser("render-telemetry", help="Per-engine render telemetry.")

# Add near the other if-blocks in main():
if args.command == "render-catalog":
    from substrate.render import render_catalog_payload
    print(json.dumps(render_catalog_payload(runtime, engine_id=args.engine), indent=2, ensure_ascii=False))
    return 0

if args.command == "render-run":
    from substrate.render import render_dispatch
    from substrate.render_engines.base import RenderRequest
    try:
        result = render_dispatch(
            runtime,
            RenderRequest(prompt=args.prompt, negative=args.negative, width=args.width, height=args.height, output=Path(args.output) if args.output else None),
            optimize_for=args.optimize_for,
            forced_engine=args.engine,
            use_cache=not args.no_cache,
            dry_run=args.dry_run,
        )
    except (ValueError, RenderUnavailable) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0

if args.command == "render-telemetry":
    from substrate.render import render_telemetry_payload
    print(json.dumps(render_telemetry_payload(runtime), indent=2, ensure_ascii=False))
    return 0
"""


# ---------------------------------------------------------------------------
# Web wiring (add to substrate/web.py)
# ---------------------------------------------------------------------------

"""
# Add these routes alongside the other /api/ routes:

@app.get("/api/render/catalog")
def api_render_catalog(engine_id: str | None = None) -> dict[str, Any]:
    runtime = _get_runtime()
    from substrate.render import render_catalog_payload
    return render_catalog_payload(runtime, engine_id=engine_id)


@app.post("/api/render/run")
def api_render_run(request: Request) -> dict[str, Any]:
    runtime = _get_runtime()
    from substrate.render import render_dispatch
    from substrate.render_engines.base import RenderRequest
    body = request.json() or {}
    req = RenderRequest(
        prompt=body.get("prompt", ""),
        negative=body.get("negative", ""),
        width=int(body.get("width", 1024)),
        height=int(body.get("height", 1024)),
        steps=body.get("steps"),
        guidance=body.get("guidance"),
        seed=body.get("seed"),
        num_images=int(body.get("num_images", 1)),
        mode=body.get("mode", "text_to_image"),
        source_image=Path(body["source_image"]) if body.get("source_image") else None,
        style_refs=[Path(p) for p in body.get("style_refs", [])],
        output=Path(body["output"]) if body.get("output") else None,
        extra=body.get("extra", {}),
    )
    try:
        return render_dispatch(
            runtime,
            req,
            optimize_for=body.get("optimize_for", "quality"),
            forced_engine=body.get("engine"),
            use_cache=not body.get("no_cache", False),
            dry_run=body.get("dry_run", False),
        )
    except (ValueError, RenderUnavailable) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/render/telemetry")
def api_render_telemetry() -> dict[str, Any]:
    runtime = _get_runtime()
    from substrate.render import render_telemetry_payload
    return render_telemetry_payload(runtime)
"""
