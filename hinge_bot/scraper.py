"""Capture one profile as a stack of screenshots, top to bottom."""
import time
from dataclasses import dataclass, field
from pathlib import Path
from PIL import Image
from . import config as C
from .device import Device, frames_equal, find_heart_buttons
from . import ocr


@dataclass
class Screen:
    index: int
    path: Path
    hearts: list[tuple[int, int]] = field(default_factory=list)
    image: Image.Image | None = None
    lines: list = field(default_factory=list)   # OCR lines, filled during capture

    @property
    def text(self): return ocr.screen_text(self.lines)


def scroll_to_top(dev: Device, max_swipes=15):
    prev = dev.screenshot()
    for _ in range(max_swipes):
        dev.scroll_up(); time.sleep(1.0)
        cur = dev.screenshot()
        if frames_equal(prev, cur):
            return cur
        prev = cur
    return prev


def capture_profile(dev: Device, out_dir: Path) -> list[Screen]:
    out_dir.mkdir(parents=True, exist_ok=True)
    screens: list[Screen] = []
    cur = scroll_to_top(dev)
    for i in range(C.MAX_SCREENS_PER_PROFILE):
        sc = Screen(i, out_dir / f"screen_{i:02d}.png", find_heart_buttons(cur), cur, ocr.read(cur))
        if screens and _same_view(screens[-1], sc):
            break   # the swipe moved nothing: bottom of the profile
        cur.save(sc.path)
        screens.append(sc)
        dev.scroll_down(); time.sleep(1.2)
        cur = dev.screenshot()
    return screens


def _same_view(a: Screen, b: Screen) -> bool:
    """Videos in the profile keep pixels changing, so compare layout too."""
    if frames_equal(a.image, b.image, tol=3.0):
        return True
    return a.hearts == b.hearts and a.text == b.text and (a.hearts or a.lines)


def scroll_to_screen(dev: Device, index: int) -> Image.Image:
    """Replay the same swipes so screen `index` is on screen again, then
    return a fresh screenshot for verification."""
    scroll_to_top(dev)
    for _ in range(index):
        dev.scroll_down(); time.sleep(1.2)
    return dev.screenshot()
