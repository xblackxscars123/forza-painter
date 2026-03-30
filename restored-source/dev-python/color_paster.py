from __future__ import annotations

import argparse
import colorsys
import re
import time
from dataclasses import dataclass
from typing import List, Tuple


FORZA_PROCESS_NAMES = {
    "forzahorizon5.exe",
    "forzahorizon4.exe",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Paste car color values into the currently focused game window. "
            "Provide either HEX or HSB input."
        )
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--hex",
        dest="hex_value",
        help="Color in HEX format, e.g. #FF8800 or FF8800",
    )
    source_group.add_argument(
        "--hsb",
        dest="hsb_value",
        help="Color in HSB format, e.g. 210,70,85",
    )

    parser.add_argument(
        "--target",
        choices=["hsb", "rgb"],
        default="hsb",
        help="Which field set to paste into (default: hsb)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Automatically paste values into the active window. "
            "Focus the first color field in-game before the countdown ends."
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.5,
        help="Seconds to wait before starting auto-paste when --apply is used (default: 2.5)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Press Enter after the final pasted value",
    )
    parser.add_argument(
        "--window-substring",
        default="Forza",
        help="Foreground window title must contain this text before auto-paste starts (default: Forza)",
    )
    parser.add_argument(
        "--window-timeout",
        type=float,
        default=30.0,
        help="Max seconds to wait for matching foreground window when --apply is used (default: 30)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.2,
        help="Seconds between foreground window checks (default: 0.2)",
    )
    return parser.parse_args()


@dataclass
class ColorModel:
    rgb: Tuple[int, int, int]
    hsb: Tuple[int, int, int]


def parse_hex(hex_value: str) -> Tuple[int, int, int]:
    cleaned = hex_value.strip()
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    if not re.fullmatch(r"[0-9a-fA-F]{6}", cleaned):
        raise ValueError("HEX must be exactly 6 hex digits, e.g. #FF8800")
    return tuple(int(cleaned[i : i + 2], 16) for i in (0, 2, 4))


def _normalize_hsb(h: float, s: float, b: float) -> Tuple[float, float, float]:
    if h > 1.0:
        h = h / 360.0
    if s > 1.0:
        s = s / 100.0
    if b > 1.0:
        b = b / 100.0

    if not (0.0 <= h <= 1.0 and 0.0 <= s <= 1.0 and 0.0 <= b <= 1.0):
        raise ValueError("HSB out of range. Use H: 0-360 and S/B: 0-100")
    return h, s, b


def parse_hsb(hsb_value: str) -> Tuple[int, int, int]:
    parts = [p.strip() for p in hsb_value.split(",")]
    if len(parts) != 3:
        raise ValueError("HSB must have 3 comma-separated values, e.g. 210,70,85")

    try:
        h_raw, s_raw, b_raw = (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError as exc:
        raise ValueError("HSB must contain numeric values") from exc

    h, s, b = _normalize_hsb(h_raw, s_raw, b_raw)
    r_f, g_f, b_f = colorsys.hsv_to_rgb(h, s, b)
    return (round(r_f * 255), round(g_f * 255), round(b_f * 255))


def rgb_to_hsb_rounded(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    r, g, b = rgb
    h_f, s_f, v_f = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return (round(h_f * 360), round(s_f * 100), round(v_f * 100))


def build_color_model(args: argparse.Namespace) -> ColorModel:
    if args.hex_value:
        rgb = parse_hex(args.hex_value)
    else:
        rgb = parse_hsb(args.hsb_value)
    return ColorModel(rgb=rgb, hsb=rgb_to_hsb_rounded(rgb))


def require_pywin32():
    try:
        import win32api  # type: ignore
        import win32clipboard  # type: ignore
        import win32con  # type: ignore
        import win32gui  # type: ignore
        import win32process  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency for clipboard/keyboard automation. "
            "Install with: python -m pip install -r restored-source/dev-python/requirements.txt"
        ) from exc
    return win32api, win32clipboard, win32con, win32gui, win32process


def set_clipboard_text(text: str, win32clipboard) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text)
    finally:
        win32clipboard.CloseClipboard()


def tap_key(vk_code: int, win32api, win32con) -> None:
    win32api.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.02)
    win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)


def ctrl_v(win32api, win32con) -> None:
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    time.sleep(0.02)
    tap_key(ord("V"), win32api, win32con)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def wait_for_window_focus(
    window_substring: str,
    timeout: float,
    poll_interval: float,
    win32gui,
    win32process,
) -> bool:
    try:
        import psutil  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'psutil'. Install with: "
            "python -m pip install -r restored-source/dev-python/requirements.txt"
        ) from exc

    needle = window_substring.strip().lower()
    if not needle:
        return True

    deadline = time.time() + max(0.0, timeout)
    interval = max(0.05, poll_interval)

    while time.time() <= deadline:
        hwnd = win32gui.GetForegroundWindow()
        title = (win32gui.GetWindowText(hwnd) or "").lower()
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = psutil.Process(pid).name().lower()
        except Exception:
            proc_name = ""

        if proc_name in FORZA_PROCESS_NAMES and needle in title:
            return True
        time.sleep(interval)
    return False


def paste_triplet(
    values: List[int],
    delay: float,
    confirm: bool,
    window_substring: str,
    window_timeout: float,
    poll_interval: float,
    win32api,
    win32clipboard,
    win32con,
    win32gui,
    win32process,
) -> None:
    print(
        f"Waiting for active window containing '{window_substring}' "
        f"(timeout {window_timeout:.1f}s)..."
    )
    if not wait_for_window_focus(window_substring, window_timeout, poll_interval, win32gui, win32process):
        raise RuntimeError(
            "Timed out waiting for active Forza window. "
            "Bring Forza Horizon to foreground and make sure the title contains "
            f"'{window_substring}', then try again."
        )

    print(f"Matched active window. Starting in {delay:.1f}s. Focus the first color field now...")
    time.sleep(max(0.0, delay))

    for index, value in enumerate(values):
        set_clipboard_text(str(value), win32clipboard)
        ctrl_v(win32api, win32con)
        if index < len(values) - 1:
            time.sleep(0.04)
            tap_key(win32con.VK_TAB, win32api, win32con)
        time.sleep(0.05)

    if confirm:
        tap_key(win32con.VK_RETURN, win32api, win32con)


def main() -> int:
    args = parse_args()

    try:
        model = build_color_model(args)
    except ValueError as exc:
        print(str(exc))
        return 2

    print(f"RGB: {model.rgb[0]}, {model.rgb[1]}, {model.rgb[2]}")
    print(f"HSB: {model.hsb[0]}, {model.hsb[1]}, {model.hsb[2]}")

    values = list(model.hsb if args.target == "hsb" else model.rgb)

    try:
        win32api, win32clipboard, win32con, win32gui, win32process = require_pywin32()
        set_clipboard_text(",".join(str(v) for v in values), win32clipboard)
    except RuntimeError as exc:
        print(str(exc))
        return 2

    print(f"Copied to clipboard ({args.target.upper()}): {values[0]}, {values[1]}, {values[2]}")

    if args.apply:
        try:
            paste_triplet(
                values,
                args.delay,
                args.confirm,
                args.window_substring,
                args.window_timeout,
                args.poll_interval,
                win32api,
                win32clipboard,
                win32con,
                win32gui,
                win32process,
            )
        except RuntimeError as exc:
            print(str(exc))
            return 2
        print("Applied values to the active window.")
    else:
        print("Apply mode not used. Run with --apply to auto-paste into active color fields.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
