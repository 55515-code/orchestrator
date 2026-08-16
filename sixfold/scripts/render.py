#!/usr/bin/env python3
"""Render a symbol to all output variants."""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from geometry.elements import ELEMENTS  # noqa: E402
from rendering.renderer import render_symbol, render_transparent, svg_export  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "output"




def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("element", nargs="?", default="all", choices=["all"] + list(ELEMENTS))
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--masters", action="store_true")
    args = ap.parse_args()

    names = list(ELEMENTS) if args.element == "all" else [args.element]
    for name in names:
        sym = ELEMENTS[name]()
        d = OUT / "masters" if args.masters else OUT
        d.mkdir(parents=True, exist_ok=True)
        img = render_symbol(sym, scale=args.scale)
        p = d / f"{name}-master.png"
        img.save(p)
        print(f"saved {p} ({img.size})")
        t = render_transparent(sym, scale=args.scale)
        tp = d / f"{name}-transparent.png"
        t.save(tp)
        print(f"saved {tp}")
        svg = OUT / "svg" / f"{name}.svg"
        svg.parent.mkdir(parents=True, exist_ok=True)
        svg_export(sym, svg)
        print(f"saved {svg}")


if __name__ == "__main__":
    main()
