#!/usr/bin/env python3
"""
image_pipeline.py — Image prep pipeline for Forza Painter decals

Flow per image:
  1. Download (if URL)
  2. Quality check (resolution + blur)
  3. Upscale with waifu2x-ncnn-vulkan (optional)
  4. Remove background with rembg
  5. Auto-crop to non-transparent bounding box
  6. Export as PNG
  7. Optimize with oxipng (lossless, no downscale)

Usage:
  python image_pipeline.py image.png
  python image_pipeline.py https://example.com/img.jpg
  python image_pipeline.py *.png --output ./out
  python image_pipeline.py urls.txt          # text file, one URL per line
  python image_pipeline.py --gui             # launch drag-and-drop GUI

Requirements:
  pip install -r requirements.txt

Waifu2x (optional):
  Download waifu2x-ncnn-vulkan from https://github.com/nihui/waifu2x-ncnn-vulkan/releases
  Add it to PATH or pass --waifu2x <path>
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# Image formats accepted as input
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".jfif", ".webp",
    ".bmp", ".gif", ".tiff", ".tif", ".ico",
    ".tga", ".ppm", ".pgm", ".pnm", ".avif",
    ".heic", ".heif", ".jp2", ".j2k", ".dds",
    ".pcx", ".sgi", ".hdr", ".exr",
})

# Content-Type → file extension for downloads
_MIME_EXT: dict[str, str] = {
    "image/jpeg":                  ".jpg",
    "image/jpg":                   ".jpg",
    "image/png":                   ".png",
    "image/webp":                  ".webp",
    "image/gif":                   ".gif",
    "image/bmp":                   ".bmp",
    "image/x-bmp":                 ".bmp",
    "image/tiff":                  ".tiff",
    "image/x-tiff":                ".tiff",
    "image/avif":                  ".avif",
    "image/heic":                  ".heic",
    "image/heif":                  ".heif",
    "image/x-icon":                ".ico",
    "image/vnd.microsoft.icon":    ".ico",
    "image/x-tga":                 ".tga",
    "image/x-targa":               ".tga",
    "image/jp2":                   ".jp2",
    "image/svg+xml":               ".svg",
}

# ── Lazy imports (so --help works without all deps installed) ─────────────────

def _import_deps():
    global requests, Image, rembg, oxipng, cv2, np
    try:
        import requests as _r; requests = _r
        from PIL import Image as _i; Image = _i
        import rembg as _rb; rembg = _rb
        import oxipng as _ox; oxipng = _ox
        import cv2 as _cv; cv2 = _cv
        import numpy as _np; np = _np
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}")
        print("Run:  pip install -r requirements.txt")
        sys.exit(1)


# ── Quality check ─────────────────────────────────────────────────────────────

MIN_RESOLUTION = (256, 256)   # warn below this
BLUR_THRESHOLD = 80.0         # Laplacian variance; lower = blurrier

def _load_cv2(path: Path):
    """Load an image as a BGR numpy array, falling back to PIL for formats
    that OpenCV cannot read natively (TIFF with exotic compression, AVIF,
    HEIC, ICO, TGA, WebP on older builds, etc.)."""
    img_cv = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img_cv is not None:
        return img_cv
    # cv2 failed — load via PIL and convert to BGR numpy array
    try:
        pil = Image.open(path)
        # For animated formats take the first frame
        if hasattr(pil, "n_frames") and pil.n_frames > 1:
            pil.seek(0)
        pil = pil.convert("RGB")
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def check_quality(path: Path) -> dict:
    img_cv = _load_cv2(path)
    if img_cv is None:
        return {"ok": False, "reason": "Could not read image"}

    h, w = img_cv.shape[:2]
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

    issues = []
    if w < MIN_RESOLUTION[0] or h < MIN_RESOLUTION[1]:
        issues.append(f"low resolution ({w}×{h})")
    if blur_score < BLUR_THRESHOLD:
        issues.append(f"blurry (score {blur_score:.1f})")

    return {
        "ok": not issues,
        "resolution": (w, h),
        "blur_score": blur_score,
        "issues": issues,
    }


# ── Step 1: Download ──────────────────────────────────────────────────────────

def download(url: str, dest_dir: Path) -> Path:
    url_path = Path(urlparse(url).path)
    raw_stem = url_path.stem or "image"
    raw_ext  = url_path.suffix.lower()

    # Keep only safe filename characters in the stem
    safe_stem = "".join(c for c in raw_stem if c.isalnum() or c in "._-") or "image"

    print(f"  Downloading {url}")
    r = requests.get(url, timeout=30, stream=True,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    # Prefer URL extension; fall back to Content-Type header
    if raw_ext in SUPPORTED_EXTENSIONS:
        ext = raw_ext
    else:
        ct = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
        ext = _MIME_EXT.get(ct, ".jpg")

    dest = dest_dir / f"{safe_stem}{ext}"
    with open(dest, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    return dest


# ── Step 2: Convert to PNG ────────────────────────────────────────────────────

def to_png(src: Path, dest: Path) -> Path:
    img = Image.open(src)

    # For animated formats (GIF, APNG, WEBP) take only the first frame
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
        img = img.copy()

    mode = img.mode

    if mode == "CMYK":
        # CMYK JPEGs invert colours if fed straight to convert("RGBA")
        img = img.convert("RGB").convert("RGBA")
    elif mode in ("I", "F"):
        # 32-bit integer / float — normalise to 8-bit greyscale first
        import numpy as _np_local
        arr = _np_local.array(img, dtype=float)
        lo, hi = arr.min(), arr.max()
        if hi > lo:
            arr = (arr - lo) / (hi - lo) * 255
        else:
            arr = _np_local.zeros_like(arr)
        img = Image.fromarray(arr.astype("uint8"), mode="L").convert("RGBA")
    elif mode == "P":
        # Palette mode — convert to RGBA so transparency is preserved correctly
        img = img.convert("RGBA")
    elif mode not in ("RGBA",):
        img = img.convert("RGBA")

    img.save(dest, "PNG")
    return dest


# ── Step 3: Upscale with waifu2x ─────────────────────────────────────────────

def _find_waifu2x() -> str | None:
    for candidate in [
        r"C:\Users\julia\OneDrive\Documents\GitHub\waifu2x-ncnn-vulkan\build\Release\waifu2x-ncnn-vulkan.exe",
        "waifu2x-ncnn-vulkan",
        "waifu2x-ncnn-vulkan.exe",
        r"C:\waifu2x-ncnn-vulkan\waifu2x-ncnn-vulkan.exe",
        str(Path.home() / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan.exe"),
    ]:
        found = shutil.which(candidate) or (Path(candidate).exists() and candidate)
        if found:
            return candidate
    return None


def _find_waifu2x_models(exe: str) -> str | None:
    """Return the models-cunet folder next to or near the exe, if it exists."""
    exe_path = Path(exe)
    # Preferred model: cunet (best quality). Fall back to other bundled models.
    model_names = ["models-cunet", "models-upconv_7_anime_style_art_rgb", "models-upconv_7_photo"]
    search_roots = [
        exe_path.parent,
        exe_path.parent.parent,
        exe_path.parent.parent.parent,
        exe_path.parent / "models",
        exe_path.parent.parent / "models",
        exe_path.parent.parent.parent / "models",
    ]
    for root in search_roots:
        for name in model_names:
            candidate = root / name
            if candidate.is_dir():
                return str(candidate)
    return None


def upscale(src: Path, dest: Path, scale: int = 2, exe: str | None = None) -> Path:
    binary = exe or _find_waifu2x()
    if not binary:
        print("  [SKIP] waifu2x-ncnn-vulkan not found — skipping upscale")
        shutil.copy(src, dest)
        return dest
    print(f"  Upscaling ×{scale} with waifu2x…")
    cmd = [binary, "-i", str(src), "-o", str(dest), "-s", str(scale), "-n", "1", "-f", "png"]
    models_dir = _find_waifu2x_models(binary)
    if models_dir:
        cmd += ["-m", models_dir]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [WARN] waifu2x failed: {result.stderr.strip()} — using original")
        shutil.copy(src, dest)
    return dest


# ── Step 4: Remove background ─────────────────────────────────────────────────

def remove_bg(src: Path, dest: Path) -> Path:
    print("  Removing background…")
    data = src.read_bytes()
    out = rembg.remove(
        data,
        alpha_matting=True,
        alpha_matting_foreground_threshold=210,  # lower = keep more fg detail
        alpha_matting_background_threshold=5,    # lower = less aggressive bg cut
        alpha_matting_erode_size=8,              # smaller = preserve more edge
    )
    dest.write_bytes(out)
    return dest


# ── Step 5: Auto-crop to non-transparent bounding box ────────────────────────

def autocrop(src: Path, dest: Path, margin: int = 2) -> Path:
    print("  Auto-cropping…")
    img = Image.open(src).convert("RGBA")
    bbox = img.getbbox()
    if bbox:
        # Add a small margin without going out of bounds
        l = max(0, bbox[0] - margin)
        t = max(0, bbox[1] - margin)
        r = min(img.width,  bbox[2] + margin)
        b = min(img.height, bbox[3] + margin)
        img = img.crop((l, t, r, b))
    img.save(dest, "PNG")
    return dest


# ── Step 6: Optimize (lossless, no downscale) ─────────────────────────────────

def optimize(path: Path, passes: int = 3) -> Path:
    print(f"  Optimizing PNG ({passes} passes)…")
    before = path.stat().st_size
    for _ in range(passes):
        oxipng.optimize(str(path), level=6)
    after = path.stat().st_size
    saved = (before - after) / 1024
    print(f"  Optimized: {before/1024:.1f} KB → {after/1024:.1f} KB  (saved {saved:.1f} KB)")
    return path


# ── Full pipeline ─────────────────────────────────────────────────────────────

def process(source: str, output_dir: Path, args: argparse.Namespace, out_stem: str | None = None) -> Path | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="imgpipe_"))

    try:
        # 1. Resolve to a local file
        if source.startswith(("http://", "https://")):
            local = download(source, tmp)
        else:
            local = Path(source)
            if not local.exists():
                print(f"  [ERROR] File not found: {local}")
                return None

        stem = out_stem if out_stem else local.stem

        # 2. Quality check
        q = check_quality(local)
        res = q.get("resolution")
        if isinstance(res, (tuple, list)) and len(res) == 2:
            res_str = "×".join(str(x) for x in res)
        else:
            res_str = "?×?"
        blur_str = f"{q.get('blur_score', 0):.1f}"
        print(f"  Quality: {res_str}px  blur={blur_str}")
        if not q.get("ok", False):
            # Some checks (e.g. unreadable images) return a 'reason' instead of 'issues'
            issues = q.get("issues")
            if issues:
                for issue in issues:
                    print(f"  [WARN] {issue}")
            else:
                reason = q.get("reason")
                if reason:
                    print(f"  [WARN] {reason}")
                else:
                    print("  [WARN] quality check failed")
            if args.skip_low_quality:
                print("  [SKIP] --skip-low-quality set — skipping")
                return None

        # 3. Convert to PNG
        png_in = tmp / f"{stem}_input.png"
        to_png(local, png_in)

        # 4. Upscale (optional)
        if args.no_upscale:
            upscaled = png_in
        else:
            upscaled = tmp / f"{stem}_upscaled.png"
            upscale(png_in, upscaled, scale=args.scale, exe=args.waifu2x)

        # 5. Remove background (optional; disabled by default)
        # Use --remove-bg to enable removal. If both flags are present,
        # explicit --remove-bg takes precedence.
        if getattr(args, "remove_bg", False):
            no_bg = tmp / f"{stem}_nobg.png"
            remove_bg(upscaled, no_bg)
        else:
            no_bg = upscaled

        # 6. Autocrop
        cropped = tmp / f"{stem}_cropped.png"
        autocrop(no_bg, cropped, margin=args.margin)

        # 7. Copy to output, optimize in-place
        suffix = getattr(args, "suffix", "") or ""
        final = output_dir / f"{stem}{suffix}.png"
        shutil.copy(cropped, final)
        optimize(final, passes=args.optimize_passes)

        kb = final.stat().st_size / 1024
        print(f"  → {final}  ({kb:.1f} KB)")
        return final

    except Exception as e:
        print(f"  [ERROR] {e}")
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Batch helper: expand text file of URLs ───────────────────────────────────

def expand_sources(raw: list[str]) -> list[str]:
    sources = []
    for s in raw:
        p = Path(s)
        # Text file of URLs (one per line)
        if p.suffix.lower() == ".txt" and p.exists():
            lines = p.read_text().splitlines()
            sources.extend(l.strip() for l in lines if l.strip() and not l.startswith("#"))
        else:
            sources.append(s)
    return sources


# ── GUI (tkinter drag-and-drop) ──────────────────────────────────────────────

def launch_gui(args: argparse.Namespace):
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, scrolledtext
        import threading
    except ImportError:
        print("[ERROR] tkinter not available")
        sys.exit(1)

    root = tk.Tk()
    root.title("Image Prep Pipeline")
    root.resizable(True, True)
    root.geometry("620x520")

    # ── Output dir row ────────────────────────────────────────────────────────
    frm_out = tk.Frame(root, pady=4)
    frm_out.pack(fill="x", padx=10)
    tk.Label(frm_out, text="Output folder:").pack(side="left")
    out_var = tk.StringVar(value=str(Path("output").resolve()))
    tk.Entry(frm_out, textvariable=out_var, width=42).pack(side="left", padx=4)
    tk.Button(frm_out, text="Browse…",
              command=lambda: out_var.set(filedialog.askdirectory() or out_var.get())
              ).pack(side="left")

    # ── Options row ───────────────────────────────────────────────────────────
    frm_opts = tk.LabelFrame(root, text="Options", pady=4)
    frm_opts.pack(fill="x", padx=10, pady=4)

    no_upscale_var = tk.BooleanVar()
    tk.Checkbutton(frm_opts, text="Skip upscale", variable=no_upscale_var).pack(side="left", padx=6)

    skip_lq_var = tk.BooleanVar()
    tk.Checkbutton(frm_opts, text="Skip low-quality", variable=skip_lq_var).pack(side="left", padx=6)

    remove_bg_var = tk.BooleanVar(value=getattr(args, "remove_bg", False))
    tk.Checkbutton(frm_opts, text="Remove background", variable=remove_bg_var).pack(side="left", padx=6)

    tk.Label(frm_opts, text="Scale:").pack(side="left", padx=(10, 2))
    scale_var = tk.IntVar(value=2)
    ttk.Combobox(frm_opts, textvariable=scale_var, values=[2, 4, 8, 16, 32],
                 width=4, state="readonly").pack(side="left")

    tk.Label(frm_opts, text="Opt passes:").pack(side="left", padx=(10, 2))
    passes_var = tk.IntVar(value=3)
    ttk.Spinbox(frm_opts, from_=1, to=10, textvariable=passes_var, width=4).pack(side="left")

    # ── URL / file drop zone ──────────────────────────────────────────────────
    tk.Label(root, text="Paste image URLs (one per line) or use Add Files:").pack(anchor="w", padx=10)
    url_box = scrolledtext.ScrolledText(root, height=10)
    url_box.pack(fill="both", expand=True, padx=10, pady=4)

    frm_btn = tk.Frame(root)
    frm_btn.pack(fill="x", padx=10, pady=4)

    def add_files():
        files = filedialog.askopenfilenames(
            filetypes=[
                ("Images",
                 " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))),
                ("All", "*.*"),
            ])
        for f in files:
            url_box.insert("end", f + "\n")

    tk.Button(frm_btn, text="Add Files…", command=add_files).pack(side="left", padx=4)

    log_box = scrolledtext.ScrolledText(root, height=8, state="disabled", bg="#1e1e1e", fg="#d4d4d4")
    log_box.pack(fill="both", expand=False, padx=10, pady=4)

    def log(msg: str):
        log_box.config(state="normal")
        log_box.insert("end", msg + "\n")
        log_box.see("end")
        log_box.config(state="disabled")

    def run():
        raw = [l.strip() for l in url_box.get("1.0", "end").splitlines() if l.strip()]
        if not raw:
            log("[WARN] No sources entered.")
            return

        # Build a namespace mimicking CLI args
        ns = argparse.Namespace(
            no_upscale=no_upscale_var.get(),
            scale=scale_var.get(),
            waifu2x=args.waifu2x,
            skip_low_quality=skip_lq_var.get(),
            margin=args.margin,
            optimize_passes=passes_var.get(),
            remove_bg=remove_bg_var.get(),
            suffix=getattr(args, "suffix", ""),
        )
        out = Path(out_var.get())
        sources = expand_sources(raw)

        def worker():
            # Redirect stdout to log
            import io
            class _Redirect:
                def write(self, msg):
                    if msg.strip():
                        root.after(0, log, msg.rstrip())
                def flush(self): pass

            old_stdout = sys.stdout
            sys.stdout = _Redirect()
            try:
                for i, src in enumerate(sources, 1):
                    root.after(0, log, f"\n[{i}/{len(sources)}] {src}")
                    process(src, out, ns)
                root.after(0, log, f"\nAll done. Output: {out.resolve()}")
            finally:
                sys.stdout = old_stdout

        threading.Thread(target=worker, daemon=True).start()

    tk.Button(frm_btn, text="Run Pipeline", bg="#2d7d46", fg="white",
              font=("Segoe UI", 10, "bold"), command=run).pack(side="right", padx=4)

    root.mainloop()


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Image prep pipeline: download → upscale → remove bg → crop → optimize PNG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("sources", nargs="*",
                        help="File paths, URLs, or a .txt file of URLs (one per line)")
    parser.add_argument("-o", "--output", default="output",
                        help="Output directory (default: ./output)")
    parser.add_argument("--gui", action="store_true",
                        help="Launch drag-and-drop GUI")
    parser.add_argument("--no-upscale", action="store_true",
                        help="Skip Waifu2x upscaling step")
    parser.add_argument("--scale", type=int, default=2, choices=[2, 4, 8, 16, 32],
                        help="Waifu2x upscale factor (default: 2)")
    parser.add_argument("--waifu2x", metavar="PATH",
                        help="Path to waifu2x-ncnn-vulkan executable")
    parser.add_argument("--skip-low-quality", action="store_true",
                        help="Skip images that fail the quality check")
    parser.add_argument("--margin", type=int, default=2, metavar="PX",
                        help="Transparent-crop margin in pixels (default: 2)")
    parser.add_argument("--optimize-passes", type=int, default=3, metavar="N",
                        help="Number of oxipng optimization passes (default: 3)")
    parser.add_argument("--prefix", metavar="PREFIX",
                        help="Output filename prefix + index instead of source name (e.g. 'run2-' → run2-1.png, run2-2.png…)")
    parser.add_argument("--remove-bg", dest="remove_bg", action="store_true",
                        help="Enable background removal step (use rembg)")
    parser.add_argument("--no-remove-bg", dest="no_remove_bg", action="store_true",
                        help="(Deprecated) Skip background removal (kept for compatibility)")
    parser.add_argument("--suffix", metavar="SUFFIX", default="",
                        help="Append text to output filenames, e.g. '_raw' → image_raw.png")

    args = parser.parse_args()

    _import_deps()

    if args.gui or not args.sources:
        launch_gui(args)
        return

    sources = expand_sources(args.sources)
    output_dir = Path(args.output)
    ok = 0

    for i, src in enumerate(sources, 1):
        print(f"\n[{i}/{len(sources)}] {src}")
        result = process(src, output_dir, args, out_stem=args.prefix + str(i) if args.prefix else None)
        if result:
            ok += 1

    print(f"\nFinished: {ok}/{len(sources)} succeeded.  Output: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
