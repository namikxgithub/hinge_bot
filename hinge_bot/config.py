"""Edit this file before running. bot.py refuses to start while PERSONA still
contains the FILL_ME marker."""

MODEL = "claude-opus-5"

# ---- Who you are. The model writes comments in your voice, so be concrete. ----
PERSONA = """
Name: Namik.
Voice: plain, dry, curious. Short sentences. Talks like a normal person texting, not like a copywriter.
Do not state any facts about Namik's job, age, city or hobbies; nothing is known. Comments must be built entirely from what the other person wrote.
Looking for: a long-term relationship.
"""

# ---- Skip rules. Plain English, the model applies them. ----
CRITERIA = """
Do not skip anyone. Every profile gets a like and a comment. Pick the most specific prompt on the profile; if there are no prompt answers, comment on a photo instead and set target_prompt_index to a photo card entry.
"""

# ---- Pacing (seconds). Randomised uniformly within each range. ----
DELAY_READ_PROFILE = (8, 25)      # after the profile is on screen, before acting
DELAY_BETWEEN_TAPS = (2, 5)
DELAY_BETWEEN_PROFILES = (40, 90)
MAX_LIKES_PER_SESSION = 1000

# ---- Screen geometry (1440x3120). Re-measure if you change phones. ----
SCREEN_W, SCREEN_H = 1440, 3120
CONTENT_TOP, CONTENT_BOTTOM = 340, 2830   # crop out status/filter bar and nav bar
X_BUTTON = (190, 2645)                     # fixed "skip" button, bottom-left
HEART_RADIUS = 70                          # dark circle around the like button
SWIPE_X = 720
SWIPE_UP = (2400, 500, 900)                # from_y, to_y, duration_ms (scroll down the profile)
SWIPE_DOWN = (1000, 2300, 900)             # scroll back to top
MAX_SCREENS_PER_PROFILE = 14

# ---- Model backend ----
BACKEND = "ollama"                 # "ollama" (free, local) or "anthropic" (API key, paid)
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2.5vl:7b"
OLLAMA_NUM_CTX = 16384
OLLAMA_TIMEOUT = 1800              # seconds; CPU inference on ten screenshots is slow
IMAGE_WIDTH = 448                  # width screenshots are sent at (smaller = faster locally)
