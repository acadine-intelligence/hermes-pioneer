#!/usr/bin/env python3
"""Build desktop/plugin.js from desktop_src/plugin.src.js.

The Desktop app loads one plain file, so the wordmark travels inside it as a data URI.
  --check         fail when desktop/plugin.js is out of date
  --art FILE      inline FILE as the page background (a personal build; the default has no image)
  -o FILE         write somewhere else (use with --art, so the repo copy stays the default build)
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "desktop_src" / "plugin.src.js"
OUT = ROOT / "desktop" / "plugin.js"
WORDMARK = ROOT / "desktop_src" / "assets" / "pioneer-wordmark.svg"


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def build(art: Path | None = None) -> str:
    text = SRC.read_text(encoding="utf-8")
    art_uri = ""
    if art is not None:
        mime = mimetypes.guess_type(art.name)[0] or {".avif": "image/avif", ".webp": "image/webp"}.get(art.suffix.lower())
        if not mime or not mime.startswith("image/"):
            raise SystemExit(f"{art} is not an image this build knows")
        art_uri = f"data:{mime};base64,{_b64(art)}"
    for token, value in {"__PIONEER_WORDMARK__": _b64(WORDMARK), "__PIONEER_ART__": art_uri}.items():
        if text.count(token) != 1:
            raise SystemExit(f"{SRC.name} must hold {token} exactly once, found {text.count(token)}")
        text = text.replace(token, value)
    return "// Built by scripts/build_desktop.py from desktop_src/plugin.src.js. Edit the source, then rebuild.\n" + text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--art", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args()
    if args.art and not args.out:
        raise SystemExit("--art needs -o: the repo copy stays the default build with no image")
    built = build(args.art)
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != built:
            print("desktop/plugin.js is out of date. Run: python3 scripts/build_desktop.py")
            return 1
        print("desktop/plugin.js is up to date")
        return 0
    out = args.out or OUT
    out.write_text(built, encoding="utf-8")
    print(f"wrote {out} ({len(built)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
