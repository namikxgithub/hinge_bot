"""Find the comment composer's text field and Send button. OCR first
(fast, deterministic); the vision model only if OCR sees no Send button."""
from .device import downscale_jpeg
from . import ocr
from . import config as C


def locate(img) -> dict:
    lines = ocr.read(img, keep_all=True)
    text = ocr.screen_text(lines)
    state = ocr.classify_text(text)
    send = next((l for l in lines if ocr.norm(l.text).startswith("send") and l.cy > C.SCREEN_H // 3), None)
    field = next((l for l in lines if "add a comment" in ocr.norm(l.text) or "write a comment" in ocr.norm(l.text)
                  or ocr.norm(l.text).startswith("comment")), None)
    if send:
        # text field: the placeholder if present, else the text block just above the Send button
        if field is None:
            above = [l for l in lines if 0 < send.y0 - l.cy < 900 and l is not send]
            field = above[-1] if above else None
        return {"state": "composer", "send_button": (send.cx, send.cy),
                "text_field": (field.cx, field.cy) if field else (C.SCREEN_W // 2, send.y0 - 300),
                "typed_text": text, "notes": "ocr"}
    if state == "profile" and any("send" in ocr.norm(l.text) for l in lines):
        state = "other"
    return {"state": state, "send_button": None, "text_field": None, "typed_text": text, "notes": "ocr, no send button"}


def comment_visible(screen_text: str, comment: str) -> bool:
    head = " ".join(ocr.norm(comment).split()[:4])
    return head in " ".join(ocr.norm(screen_text).split())
