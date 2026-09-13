"""Thin adb wrapper plus pixel-level element finders.

Hinge's UI is a Compose tree that exposes nothing to `uiautomator dump`, so
everything here works from screenshots: fixed geometry for the X button, a
ring-scan for the dark circular like buttons, and frame comparison to detect
scroll boundaries."""
import io, math, shlex, subprocess, time
from PIL import Image
import numpy as np
from . import config as C


class Device:
    def __init__(self, serial: str | None = None):
        self.base = ["adb"] + (["-s", serial] if serial else [])

    # ---- raw adb ----
    def sh(self, *args: str, timeout=20) -> str:
        r = subprocess.run(self.base + ["shell", *args], capture_output=True, timeout=timeout)
        return r.stdout.decode(errors="replace")

    def connected(self) -> bool:
        out = subprocess.run(self.base + ["get-state"], capture_output=True).stdout.decode()
        return out.strip() == "device"

    def foreground(self) -> str:
        out = self.sh("dumpsys", "window")
        for line in out.splitlines():
            if "mCurrentFocus" in line:
                return line.strip()
        return ""

    def hinge_in_front(self) -> bool:
        return "co.hinge.app" in self.foreground()

    def screenshot(self) -> Image.Image:
        r = subprocess.run(self.base + ["exec-out", "screencap", "-p"], capture_output=True, timeout=20)
        return Image.open(io.BytesIO(r.stdout)).convert("RGB")

    def tap(self, x: int, y: int):
        self.sh("input", "tap", str(int(x)), str(int(y)))

    def swipe(self, x1, y1, x2, y2, ms):
        self.sh("input", "swipe", *map(str, map(int, (x1, y1, x2, y2, ms))))

    def scroll_down(self):
        a, b, ms = C.SWIPE_UP
        self.swipe(C.SWIPE_X, a, C.SWIPE_X, b, ms)

    def scroll_up(self):
        a, b, ms = C.SWIPE_DOWN
        self.swipe(C.SWIPE_X, a, C.SWIPE_X, b, ms)

    def back(self):
        self.sh("input", "keyevent", "KEYCODE_BACK")

    def type_text(self, text: str):
        """`input text` only handles ASCII; spaces must be %s; the rest is
        single-quoted for the device shell so punctuation is safe."""
        clean = sanitize_for_input(text)
        for chunk in [clean[i:i + 120] for i in range(0, len(clean), 120)]:
            self.sh("input", "text", shlex.quote(chunk.replace(" ", "%s")))
            time.sleep(0.3)


def sanitize_for_input(text: str) -> str:
    text = text.replace("’", "'").replace("“", '"').replace("”", '"').replace("—", "-")
    text = text.encode("ascii", "ignore").decode()
    return " ".join(text.split())


# ---- pixel finders ----
def _dark(p): return int(p[0]) + int(p[1]) + int(p[2]) < 150
def _light(p): return int(p[0]) + int(p[1]) + int(p[2]) > 300


def find_heart_buttons(img: Image.Image) -> list[tuple[int, int]]:
    """Dark filled circles of radius ~HEART_RADIUS with a light surround.
    Returns centres, top to bottom. Excludes the nav bar and the X button."""
    px = img.load(); W, H = img.size; r = C.HEART_RADIUS
    hits = []
    for y in range(C.CONTENT_TOP, C.CONTENT_BOTTOM, 6):
        for x in range(r + 40, W - r - 40, 6):
            if not _dark(px[x, y]):
                continue
            if all(_dark(px[x + int(r * math.cos(math.radians(a))), y + int(r * math.sin(math.radians(a)))]) for a in range(0, 360, 45)) and \
               all(_light(px[min(W - 1, max(0, x + int((r + 40) * math.cos(math.radians(a))))), min(H - 1, max(0, y + int((r + 40) * math.sin(math.radians(a)))))]) for a in range(0, 360, 45)):
                hits.append((x, y))
    clusters: list[list] = []
    for x, y in hits:
        for c in clusters:
            if abs(c[0] - x) < 90 and abs(c[1] - y) < 90:
                c[2].append((x, y)); break
        else:
            clusters.append([x, y, [(x, y)]])
    out = []
    for c in clusters:
        xs = [p[0] for p in c[2]]; ys = [p[1] for p in c[2]]
        cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
        if abs(cx - C.X_BUTTON[0]) < 200 and abs(cy - C.X_BUTTON[1]) < 200:
            continue
        out.append((cx, cy))
    return sorted(out, key=lambda p: p[1])


def x_button_present(img: Image.Image) -> bool:
    """White circle with a dark X at the fixed bottom-left position."""
    px = img.load(); x, y = C.X_BUTTON
    centre_dark = _dark(px[x, y]) or _dark(px[x + 12, y + 12]) or _dark(px[x - 12, y - 12])
    ring_light = all(_light(px[x + int(100 * math.cos(math.radians(a))), y + int(100 * math.sin(math.radians(a)))]) for a in range(0, 360, 60))
    return centre_dark and ring_light


def content_crop(img: Image.Image) -> Image.Image:
    return img.crop((0, C.CONTENT_TOP, C.SCREEN_W, C.CONTENT_BOTTOM))


def frames_equal(a: Image.Image, b: Image.Image, tol=2.0) -> bool:
    x = np.asarray(content_crop(a).resize((180, 320)), dtype=np.int16)
    y = np.asarray(content_crop(b).resize((180, 320)), dtype=np.int16)
    return float(np.abs(x - y).mean()) < tol


def downscale_jpeg(img: Image.Image, width=720, quality=80) -> bytes:
    w, h = img.size
    im = img.resize((width, int(h * width / w)))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=quality)
    return buf.getvalue()
