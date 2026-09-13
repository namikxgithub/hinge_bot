"""Act on an approved decision. Every tap is preceded by a screenshot check;
if the screen is not what we expect, we stop and report instead of guessing."""
import random, time
from pathlib import Path
from .device import Device, find_heart_buttons, x_button_present, sanitize_for_input
from .scraper import scroll_to_screen
from .locate import locate, comment_visible
from .decide import heart_below_text, text_on_screen
from . import config as C


class StepFailed(Exception):
    pass


def pause(rng=C.DELAY_BETWEEN_TAPS):
    time.sleep(random.uniform(*rng))


def skip_profile(dev: Device, log_dir: Path):
    img = dev.screenshot()
    if not x_button_present(img):
        img.save(log_dir / "fail_no_x_button.png")
        raise StepFailed("X button not where expected")
    dev.tap(*C.X_BUTTON)
    pause()


def send_like(dev: Device, heart_screen: int, heart: tuple[int, int], comment: str, log_dir: Path, target_text: str | None = None):
    comment = sanitize_for_input(comment)
    if not comment:
        raise StepFailed("empty comment after sanitising")

    # 1. get the right part of the profile back on screen and re-find the button
    #    from the answer text itself; scroll offsets drift between passes.
    img = scroll_to_screen(dev, heart_screen)
    btn = None
    for attempt in range(3):
        hearts = find_heart_buttons(img)
        if target_text:
            btn = heart_below_text(img, hearts, target_text)
        else:
            near = [h for h in hearts if abs(h[0] - heart[0]) < 120 and abs(h[1] - heart[1]) < 150]
            btn = near[0] if near else None
        if btn:
            break
        (dev.scroll_down if attempt == 0 else dev.scroll_up)(); time.sleep(1.2)
        img = dev.screenshot()
    if not btn:
        img.save(log_dir / "fail_heart_not_found.png")
        raise StepFailed(f"like button for '{(target_text or '')[:30]}' not found on screen")
    dev.tap(*btn); pause()

    # 2. composer must be open, and must show the card we meant
    img = dev.screenshot(); img.save(log_dir / "after_heart.png")
    loc = locate(img)
    if loc["state"] != "composer" or not loc["text_field"] or not loc["send_button"]:
        raise StepFailed(f"expected comment composer, got {loc['state']}: {loc['notes']}")
    if target_text and not text_on_screen(img, target_text):
        dev.back(); pause((1, 2))
        raise StepFailed("composer opened on a different card than the comment is about; backed out")
    dev.tap(*loc["text_field"]); pause((1, 2))
    dev.type_text(comment); pause((1, 2))

    # 3. verify what was typed before sending
    img = dev.screenshot(); img.save(log_dir / "after_typing.png")
    loc = locate(img)
    if loc["state"] != "composer" or not loc["send_button"] or not comment_visible(loc.get("typed_text") or "", comment):
        dev.back()
        raise StepFailed("typed comment not visible on screen, backed out")
    dev.tap(*loc["send_button"]); pause((3, 5))

    # 4. confirm we left the composer
    img = dev.screenshot(); img.save(log_dir / "after_send.png")
    loc = locate(img)
    if loc["state"] == "composer":
        raise StepFailed("still on composer after tapping send")
    return loc["state"]
