from __future__ import annotations

import argparse
import ctypes
import importlib
import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Tuple


@dataclass
class Color:
    r: int
    g: int
    b: int
    a: int = 255

    def as_bytes(self) -> bytes:
        return (
            struct.pack("B", self.r)
            + struct.pack("B", self.g)
            + struct.pack("B", self.b)
            + struct.pack("B", self.a)
        )


@dataclass
class Shape:
    type_id: int
    x: int
    y: int
    w: int
    h: int
    rot_deg: int
    color: Color
    is_mask: bool = False


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Modernized dev runner for legacy Forza Painter geometry injection."
    )
    parser.add_argument("--input", required=True, help="Path to generated geometry json")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show OpenCV preview before optional injection",
    )
    parser.add_argument(
        "--preview-path",
        default="preview.png",
        help="Where to save preview image (default: preview.png)",
    )
    parser.add_argument(
        "--inject",
        action="store_true",
        help="Attempt memory injection into Forza process",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Do not open OpenCV window (still saves preview if --preview)",
    )
    return parser.parse_args()


def load_geometry(path: Path) -> Tuple[int, int, List[Shape], Color]:
    with path.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid json: {exc}") from exc

    if "shapes" not in data or not data["shapes"]:
        raise ValueError("Invalid geometry: missing shapes array")

    header = data["shapes"][0]
    if "data" not in header or len(header["data"]) < 4:
        raise ValueError("Invalid geometry header data")
    if "color" not in header or len(header["color"]) != 4:
        raise ValueError("Invalid geometry header color")

    image_w, image_h = map(int, header["data"][2:4])
    bg_color = Color(*map(int, header["color"]))

    shapes: List[Shape] = []

    if bg_color.a > 0:
        shapes.append(
            Shape(
                type_id=1,
                x=image_w // 2,
                y=image_h // 2,
                w=image_w,
                h=image_h,
                rot_deg=0,
                color=bg_color,
                is_mask=False,
            )
        )

    for item in data["shapes"][1:]:
        shape_type = int(item.get("type", -1))
        if shape_type != 16:
            # Keep strict behavior for now to match legacy imports.
            continue

        raw = item.get("data")
        color = item.get("color")
        if not raw or len(raw) != 5 or not color or len(color) != 4:
            continue

        x, y, w, h, rot_deg = map(int, raw)
        r, g, b, a = map(int, color)
        shapes.append(
            Shape(
                type_id=16,
                x=x,
                y=y,
                w=w,
                h=h,
                rot_deg=rot_deg,
                color=Color(r, g, b, a),
                is_mask=False,
            )
        )

    if not shapes:
        raise ValueError("No supported shapes found in geometry")

    return image_w, image_h, shapes, bg_color


def add_mask_shapes(image_w: int, image_h: int, shapes: List[Shape]) -> None:
    shapes.append(
        Shape(1, -(image_w // 4), image_h // 2, image_w // 2, int(image_h * 1.5), 0, Color(0, 0, 0, 255), True)
    )
    shapes.append(
        Shape(1, image_w + (image_w // 4), image_h // 2, image_w // 2, int(image_h * 1.5), 0, Color(0, 0, 0, 255), True)
    )
    shapes.append(
        Shape(1, image_w // 2, -(image_h // 4), image_w * 2, image_h // 2, 0, Color(0, 0, 0, 255), True)
    )
    shapes.append(
        Shape(1, image_w // 2, image_h + (image_h // 4), image_w * 2, image_h // 2, 0, Color(0, 0, 0, 255), True)
    )


def require_module(module_name: str, package_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Missing dependency '{module_name}'. Install dependencies with: "
            "python -m pip install -r restored-source/dev-python/requirements.txt"
        ) from exc


def build_preview(image_w: int, image_h: int, shapes: List[Shape], bg_color: Color, cv2: Any, np: Any) -> Any:
    preview = np.zeros((image_h, image_w, 3), np.uint8)
    preview = cv2.rectangle(
        preview,
        (0, 0),
        (image_w, image_h),
        (bg_color.b, bg_color.g, bg_color.r, bg_color.a),
        thickness=-1,
    )
    for shape in shapes:
        if shape.type_id == 16:
            preview = cv2.ellipse(
                preview,
                (shape.x, shape.y),
                (shape.h, shape.w),
                -90 + shape.rot_deg,
                0.0,
                360.0,
                (shape.color.b, shape.color.g, shape.color.r),
                thickness=-1,
            )
        elif shape.type_id == 1:
            x0 = max(0, int(shape.x - shape.w / 2))
            y0 = max(0, int(shape.y - shape.h / 2))
            x1 = min(image_w, int(shape.x + shape.w / 2))
            y1 = min(image_h, int(shape.y + shape.h / 2))
            preview = cv2.rectangle(
                preview,
                (x0, y0),
                (x1, y1),
                (shape.color.b, shape.color.g, shape.color.r),
                thickness=-1,
            )
    return preview


def get_forza_pid(psutil: Any) -> int:
    targets = {
        "ForzaHorizon5.exe",
        "forzahorizon5.exe",
        "ForzaHorizon4.exe",
        "forzahorizon4.exe",
    }
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            name = proc.info.get("name") or ""
            if name in targets:
                return int(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return -1


def inject_shapes(pid: int, shapes: List[Shape]) -> None:
    # Import legacy native bridge only when needed, so preview mode works even if
    # pywin32 is not installed.
    root = Path(__file__).resolve().parents[1] / "legacy-python"
    sys.path.insert(0, str(root))
    import native  # type: ignore

    base_addr = native.get_base_address(pid)
    start_address = base_addr + 0x08000000
    match = native.scan_block(pid, start_address, 0x02000000, b"\x12\x47\x9B\x13\x29\xD9\xA2\xB1")
    if match == -1:
        raise RuntimeError("Unsupported game version: unable to locate signature")

    pre_addr = start_address + match
    addr_a = native.dereference_pointer(pid, pre_addr + 0xB8)
    addr_b = native.dereference_pointer(pid, addr_a + 0xA58)
    c_livery = native.dereference_pointer(pid, addr_b + 0x8)
    if c_livery == 0:
        raise RuntimeError("Create Vinyl Group menu not detected")

    c_livery_group = native.dereference_pointer(pid, c_livery + 0x20)
    if c_livery_group == 0:
        raise RuntimeError("Invalid livery group pointer")

    current_livery_count = native.read_int(pid, c_livery_group + 0x5A)
    if current_livery_count < 100:
        raise RuntimeError("Template layer count too low. Load and ungroup a template first")

    c_livery_layer_table = native.dereference_pointer(pid, c_livery_group + 0x78)
    if c_livery_layer_table == 0:
        raise RuntimeError("Invalid livery layer table pointer")

    usable = min(len(shapes), current_livery_count)
    for i, shape in enumerate(shapes[:usable]):
        layer_addr = native.dereference_pointer(pid, c_livery_layer_table + (i * 0x8))

        pos_data = struct.pack("f", shape.x) + struct.pack("f", -shape.y)
        native.write_process_memory(pid, layer_addr + 0x18, pos_data)

        scale_divisor = 63 if shape.type_id == 16 else 127
        scale_data = struct.pack("f", shape.w / scale_divisor) + struct.pack("f", shape.h / scale_divisor)
        native.write_process_memory(pid, layer_addr + 0x28, scale_data)

        rot_data = struct.pack("f", 360 - shape.rot_deg)
        native.write_process_memory(pid, layer_addr + 0x50, rot_data)

        native.write_process_memory(pid, layer_addr + 0x74, shape.color.as_bytes())

        shape_id = 102 if shape.type_id == 16 else 101
        native.write_process_memory(pid, layer_addr + 0x7A, struct.pack("B", shape_id))
        native.write_process_memory(pid, layer_addr + 0x78, struct.pack("B", 1 if shape.is_mask else 0))



def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file does not exist: {input_path}")
        return 2

    try:
        image_w, image_h, shapes, bg_color = load_geometry(input_path)
    except ValueError as exc:
        print(str(exc))
        return 2

    add_mask_shapes(image_w, image_h, shapes)

    if args.preview:
        try:
            cv2 = require_module("cv2", "opencv-python")
            np = require_module("numpy", "numpy")
        except RuntimeError as exc:
            print(str(exc))
            return 2

        preview = build_preview(image_w, image_h, shapes, bg_color, cv2, np)
        preview_path = Path(args.preview_path)
        cv2.imwrite(str(preview_path), preview)
        print(f"Saved preview: {preview_path}")

        if not args.no_window:
            cv2.imshow("forza-painter dev preview", preview)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    if args.inject:
        if os.name != "nt":
            print("Injection mode is only supported on Windows")
            return 2
        if not is_admin():
            print("Run this script as Administrator for injection mode")
            return 2

        try:
            psutil = require_module("psutil", "psutil")
        except RuntimeError as exc:
            print(str(exc))
            return 2

        pid = get_forza_pid(psutil)
        if pid < 0:
            print("Forza process not found")
            return 2

        try:
            inject_shapes(pid, shapes)
        except Exception as exc:
            print(f"Injection failed: {exc}")
            return 1

        print("Injection completed")

    if not args.preview and not args.inject:
        print("No action requested. Use --preview and/or --inject")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
