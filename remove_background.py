#!/usr/bin/env python3
"""
remove_background.py — standalone background removal helper

Run this separately when you explicitly want to remove backgrounds from
existing images (useful when the main automation pipeline has removal
disabled by default).

Usage:
  python remove_background.py path/to/image.png
  python remove_background.py dir_with_images -o out_dir
  python remove_background.py img1.jpg img2.webp --suffix _nobg

This script uses the same `remove_bg` logic from `image_pipeline.py`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import image_pipeline as ip


def _gather_sources(raw_paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in raw_paths:
        pth = Path(p)
        if not pth.exists():
            print(f"[WARN] Not found: {pth}")
            continue
        if pth.is_dir():
            for f in pth.rglob("*"):
                if f.is_file() and f.suffix.lower() in ip.SUPPORTED_EXTENSIONS:
                    out.append(f)
        else:
            if pth.suffix.lower() in ip.SUPPORTED_EXTENSIONS:
                out.append(pth)
    return out


def process_file(src: Path, out_dir: Path, suffix: str, inplace: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="rembg_"))
    try:
        png_in = tmp / f"{src.stem}_input.png"
        # Ensure rembg and other deps are loaded
        ip._import_deps()
        ip.to_png(src, png_in)

        if inplace:
            dest = src.with_suffix(".png")
        else:
            dest = out_dir / f"{src.stem}{suffix}.png"

        print(f"Removing background: {src} → {dest}")
        ip.remove_bg(png_in, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="Remove backgrounds from images (uses rembg)")
    parser.add_argument("paths", nargs="+", help="Files or directories to process")
    parser.add_argument("-o", "--output", default="output_nobg", help="Output directory")
    parser.add_argument("--suffix", default="_nobg", help="Suffix for output filenames")
    parser.add_argument("--inplace", action="store_true", help="Overwrite originals (writes .png)")
    args = parser.parse_args(argv)

    sources = _gather_sources(args.paths)
    if not sources:
        print("No images found to process.")
        return 1

    for s in sources:
        try:
            process_file(s, Path(args.output), args.suffix, args.inplace)
        except Exception as e:
            print(f"[ERROR] {s}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
