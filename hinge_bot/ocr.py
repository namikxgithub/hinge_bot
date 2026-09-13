"""Local OCR (rapidocr, CPU, ~2.5 s per screen). Gives every text line with
its pixel box, which is what we use to find prompt cards and the composer."""
import difflib, re
from dataclasses import dataclass
import numpy as np
from PIL import Image
from . import config as C

_engine = None


@dataclass
class Line:
    text: str
    x0: int; y0: int; x1: int; y1: int
    conf: float
    @property
    def cx(self): return (self.x0 + self.x1) // 2
    @property
    def cy(self): return (self.y0 + self.y1) // 2


def read(img: Image.Image, keep_all=False) -> list[Line]:
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    res, _ = _engine(np.asarray(img))
    out = []
    for box, text, conf in (res or []):
        xs = [int(p[0]) for p in box]; ys = [int(p[1]) for p in box]
        ln = Line(text.strip(), min(xs), min(ys), max(xs), max(ys), float(conf))
        if not keep_all and not (C.CONTENT_TOP < ln.cy < C.CONTENT_BOTTOM):
            continue
        if len(ln.text) < 2 and not ln.text.isdigit() and not (ln.text.isalpha() and 400 < ln.cy < 800):
            continue
        if not keep_all and _occluded_by_x(ln):
            continue
        out.append(ln)
    return sorted(out, key=lambda l: (l.y0, l.x0))


def _occluded_by_x(ln: Line) -> bool:
    """The fixed X button covers the left end of lines near it, so OCR
    returns them truncated. The same lines appear whole one screen later."""
    x, y = C.X_BUTTON
    return ln.x0 < x + 150 and abs(ln.cy - y) < 200


def merged_text(per_screen: list[list[Line]], window=14) -> str:
    """One top-to-bottom stream with the overlap between screens removed."""
    out: list[str] = []
    for lines in per_screen:
        for ln in lines:
            n = norm(ln.text)
            if any(n == norm(prev) for prev in out[-window:]):
                continue
            out.append(ln.text)
    return "\n".join(out)


def profile_name(lines: list[Line]) -> str | None:
    """Name is the first tall line on the first screen, above the pronouns."""
    for ln in lines:
        if 400 < ln.cy < 800 and (ln.y1 - ln.y0) > 50 and ln.text.replace(" ", "").isalpha():
            return ln.text
    return None


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def screen_text(lines: list[Line]) -> str:
    return "\n".join(l.text for l in lines)


PAYWALL = re.compile(r"out of likes|you.?re out of|get hinge|upgrade to|hinge\+|hingex|subscribe|slow down|try again later|too many", re.I)


def classify_text(text: str) -> str:
    t = norm(text)
    if re.search(r"it.?s a match", t): return "match"
    if re.search(r"out of likes|you re out of", t): return "out_of_likes"
    if re.search(r"slow down|try again later|too many", t): return "rate_limited"
    if re.search(r"get hinge|upgrade to|hinge x|hingex|subscribe", t): return "paywall"
    return "profile"
