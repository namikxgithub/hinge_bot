# Hinge draft-and-review bot

Reads each profile in the Discover feed, has Claude draft a comment, and
waits for you to approve or edit it on a local review page before anything
is sent. Model "skip" decisions are executed without asking unless you pass
`--confirm-skips`.

## Setup

1. `pip install -r requirements.txt`
2. Model: the default backend is a free local model (Ollama + qwen2.5vl:7b
   under `~/.local/ollama`, started by run.sh). To use the Claude API
   instead, set `BACKEND = "anthropic"` in config.py and export
   `ANTHROPIC_API_KEY`.
3. Edit `hinge_bot/config.py`: fill in PERSONA and CRITERIA, check the
   pacing and the like cap.
4. Phone: USB debugging on, `adb devices` shows it, Hinge open on Discover.

## Run

    ./run.sh          # dry run
    ./run.sh --live   # real loop

Flags: `--dry-run` (capture and draft, never tap; you advance the feed by
hand), `--confirm-skips`, `--port`, `--serial`.

The review page opens at http://127.0.0.1:8765/. Each profile shows its
screenshots, the extracted prompts, the model's reasoning and an editable
draft. The bot blocks until you press "Send like" or "Skip".

Everything is logged under `runs/<timestamp>/`: screenshots per profile,
`decision.json`, and `queue.json` with the final status of each one.

## How it works, and what is fragile

- Like buttons overlaid on dark photos are not detected (the ring test needs a light surround). Only prompt-card buttons matter, and those sit on white.
- Hinge is a Compose app that exposes nothing to `uiautomator dump`, so the
  bot works from screenshots only. Like buttons are found as dark circles
  (`device.find_heart_buttons`), the X button at a fixed position
  (`config.X_BUTTON`). Both are measured for a 1440x3120 screen.
- Profile text comes from local OCR (rapidocr) at full resolution; the
  language model only sees text, which is what makes the free local model
  fast enough (about 90 s per profile on CPU). Which like button belongs to
  the chosen prompt is resolved from the OCR position of the prompt title.
- The comment composer is located by OCR too (the Send button text and the
  comment placeholder); the typed text is read back and checked before Send
  is tapped. The vision model is used only for photo-only profiles.
- The local model writes plainer comments than Claude. To use Claude
  instead, set BACKEND = "anthropic" and export ANTHROPIC_API_KEY.
- If any check fails the bot stops, saves a screenshot, and waits for you
  to press Enter after fixing the phone state. It never taps blind.
- Stops on out-of-likes / paywall / rate-limit screens, on the like cap,
  and if the same profile appears twice (the feed did not advance).
- Automating the client is against Hinge's terms. Keep the pacing, keep
  sessions short, and expect that the account can still be flagged.
