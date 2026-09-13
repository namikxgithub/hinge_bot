"""Orchestrator.

    python -m hinge_bot.bot --max-likes 15

Loop: capture profile -> Claude drafts -> you approve on http://127.0.0.1:8765
-> send or skip -> next. Model skips are executed without asking unless
--confirm-skips. --dry-run captures and drafts but never taps."""
import argparse, datetime as dt, json, random, sys, time, uuid, webbrowser
from pathlib import Path
from . import config as C
from .device import Device, x_button_present
from .scraper import capture_profile
from .decide import decide
from .review import Queue, serve_in_thread
from .sender import send_like, skip_profile, StepFailed


def log(msg):
    print(dt.datetime.now().strftime("%H:%M:%S"), msg, flush=True)


def ensure_feed(dev: Device) -> bool:
    """True if the Discover feed is showing with no comment composer open.
    Hinge's composer expands inline, so the X button alone is not proof;
    check the screen text too. Backs out of a stray composer with Back."""
    from . import ocr
    for _ in range(3):
        img = dev.screenshot()
        text = ocr.norm(ocr.screen_text(ocr.read(img, keep_all=True)))
        composer = "add a comment" in text or " send " in f" {text} " or "send priority" in text or "send like" in text
        if x_button_present(img) and not composer:
            return True
        dev.back(); time.sleep(1.5)
        if not dev.hinge_in_front():
            dev.sh("monkey", "-p", "co.hinge.app", "-c", "android.intent.category.LAUNCHER", "1"); time.sleep(4)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-likes", type=int, default=C.MAX_LIKES_PER_SESSION)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--confirm-skips", action="store_true", help="also ask before X-ing a profile")
    ap.add_argument("--dry-run", action="store_true", help="capture + draft only, never tap")
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--serial", default=None)
    a = ap.parse_args()

    if "FILL_ME" in C.PERSONA:
        sys.exit("Edit hinge_bot/config.py: PERSONA still has the FILL_ME marker.")
    if C.BACKEND == "ollama":
        from .llm import ollama_ready
        ok, why = ollama_ready()
        if not ok:
            sys.exit(f"local model not ready: {why}")
    dev = Device(a.serial)
    if not dev.connected():
        sys.exit("No adb device.")
    if not dev.hinge_in_front():
        sys.exit(f"Hinge is not in the foreground: {dev.foreground()}")
    hour = dt.datetime.now().hour
    if hour >= 23 or hour < 7:
        log("WARNING: running overnight is a detection tell; the plan said not to.")

    run_dir = Path(a.runs_dir) / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True)
    queue = Queue(run_dir / "queue.json")
    serve_in_thread(queue, run_dir, a.port)
    url = f"http://127.0.0.1:{a.port}/"
    log(f"review page: {url}")
    webbrowser.open(url)

    likes = 0; seen: set[str] = set(); n = 0
    while likes < a.max_likes:
        n += 1
        pdir = run_dir / f"p{n:03d}"
        if not ensure_feed(dev):
            log("not on the Discover feed (no X button); put Hinge on Discover and press Enter")
            if not sys.stdin.isatty(): break
            input(); continue
        log(f"profile {n}: capturing")
        screens = capture_profile(dev, pdir)
        time.sleep(random.uniform(*C.DELAY_READ_PROFILE))
        d = decide(screens)
        (pdir / "decision.json").write_text(json.dumps(d.to_dict(), indent=1))
        log(f"profile {n}: {d.name} {d.age} -> {'LIKE' if d.like else 'skip'} ({d.reason})")

        if d.screen_state != "profile":
            log(f"stopping: screen is {d.screen_state}"); break
        key = f"{d.name}|{d.prompts[0]['answer'][:40] if d.prompts else ''}"
        if key in seen:
            log("same profile as before; the last action did not advance the feed. stopping.")
            break
        seen.add(key)

        item = dict(id=uuid.uuid4().hex[:8], ts=dt.datetime.now().isoformat(timespec="seconds"),
                    name=d.name, age=d.age, basics=d.basics, prompts=d.prompts, like=d.like, reason=d.reason,
                    target_prompt_index=d.target_prompt_index, comment=d.comment,
                    screenshots=[str(s.path.relative_to(run_dir)) for s in screens],
                    status="pending" if (d.like or a.confirm_skips) else "auto_skipped", error=None)
        queue.add(item)

        if a.dry_run:
            if item["status"] == "pending":
                queue.update(item["id"], status="dry_run")
            if not sys.stdin.isatty():
                log("dry run finished (no terminal attached, stopping after one profile)"); break
            log("dry run: not tapping; move to the next profile by hand, then press Enter")
            input()
            continue

        try:
            if item["status"] == "pending":
                log("waiting for your decision on the review page")
                final = queue.wait_for_decision(item["id"])
                if final["status"] == "approved" and d.heart is not None:
                    state = send_like(dev, d.heart_screen, d.heart, final["final_comment"], pdir, d.target_text)
                    likes += 1
                    queue.update(item["id"], status="sent")
                    log(f"sent ({likes}/{a.max_likes}); screen now: {state}")
                    if state in ("out_of_likes", "paywall"):
                        log("stopping: out of likes / paywall"); break
                else:
                    skip_profile(dev, pdir)
                    queue.update(item["id"], status="skipped")
            else:
                skip_profile(dev, pdir)
        except StepFailed as e:
            log(f"step failed: {e}")
            queue.update(item["id"], status="failed", error=str(e))
            if not sys.stdin.isatty():
                log("no terminal attached; stopping after the failure. Screenshots are in " + str(pdir)); break
            log("not retrying; fix the phone state (Hinge on the discover feed) then press Enter to continue, or Ctrl-C")
            input()

        time.sleep(random.uniform(*C.DELAY_BETWEEN_PROFILES))

    log(f"done: {likes} likes sent, {n} profiles seen. Log: {run_dir}")
    if not sys.stdin.isatty():
        return
    log("review page stays up until you Ctrl-C")
    try:
        while True: time.sleep(60)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
