"""Read a captured profile (OCR text first, vision only as a fallback) and
draft a like comment. Button positions come from OCR + pixel detection, not
from the language model."""
from dataclasses import dataclass, asdict
from .llm import ask_json
from .device import downscale_jpeg
from .scraper import Screen
from . import ocr
from . import config as C

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": ["integer", "null"]},
        "basics": {"type": "string"},
        "prompts": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "answer": {"type": "string"}},
            "required": ["title", "answer"], "additionalProperties": False}},
        "like": {"type": "boolean"},
        "reason": {"type": "string"},
        "target_answer": {"type": ["string", "null"]},
        "comment": {"type": ["string", "null"]},
    },
    "required": ["name", "age", "basics", "prompts", "like", "reason", "target_answer", "comment"],
    "additionalProperties": False,
}

SYSTEM = """You receive the OCR text of one Hinge dating profile, top to bottom. You are writing a short like comment TO this person, on behalf of the sender described at the end. The profile belongs to someone else; their name is the first line of the text.

1. name: the profile owner's name (first line). age: the number next to Woman/Man. basics: job, school, religion, location, politics, languages, dating intention, as one line.
2. prompts: every prompt card as title -> answer, in order, complete. A prompt title is a short phrase in the text that introduces a longer answer written by the profile owner. Copy titles and answers exactly as they appear in the text; never invent or reword a title.
3. like and reason: follow the rules below.
4. target_answer: copy, word for word from the profile text, the first line of the prompt answer your comment is about. Prefer the answer with the most concrete, literal detail (a food, a place, a habit, a hobby, a small daily thing). Avoid answers about exes, relationships, wives or husbands, therapy, or anything sensitive.
5. comment: one or two sentences in the sender's voice about that specific detail, ending with a question. Plain ASCII, no emoji, no quotation marks, no compliments on looks, no pickup lines, nothing about the sender that is not in the persona.

--- Rules ---
""" + C.CRITERIA + """
--- The sender (the person the comment is FROM, never the profile owner) ---
""" + C.PERSONA

PHOTO_SYSTEM = """You see one screenshot of a Hinge profile that has no prompt answers, only photos. Write a like comment in the persona's voice about something concrete visible in the photo (a place, an activity, an object), not about the person's looks. At most two sentences, ends with a question, plain ASCII, no emoji.
--- Persona ---
""" + C.PERSONA
PHOTO_SCHEMA = {"type": "object", "properties": {"comment": {"type": "string"}}, "required": ["comment"], "additionalProperties": False}


@dataclass
class Decision:
    screen_state: str
    name: str
    age: int | None
    basics: str
    prompts: list
    like: bool
    reason: str
    target_prompt_index: int | None
    comment: str | None
    heart: tuple[int, int] | None = None      # full-res coordinates of the button to tap
    heart_screen: int | None = None
    target_text: str | None = None            # the answer line the comment is about (for re-finding the button)
    refused: bool = False

    def to_dict(self): return asdict(self)


def decide(screens: list[Screen]) -> Decision:
    per_screen = [s.lines if s.lines else ocr.read(s.image) for s in screens]
    all_text = "\n".join(ocr.screen_text(ls) for ls in per_screen)
    state = ocr.classify_text(all_text)
    if state != "profile":
        return Decision(state, "?", None, "", [], False, f"screen is {state}", None, None)

    body = ocr.merged_text(per_screen)
    data = ask_json(SYSTEM, [], "PROFILE TEXT:\n" + body + "\n\nRespond with the JSON object.", SCHEMA, max_tokens=600)
    if data is None:
        return Decision("profile", "?", None, "", [], False, "model declined", None, None, refused=True)
    target_answer = data.pop("target_answer", None) or ""
    d = Decision("profile", target_prompt_index=None, **data)
    real_name = ocr.profile_name(per_screen[0]) if per_screen else None
    if real_name:
        d.name = real_name

    if d.like and target_answer.strip():
        d.target_prompt_index = _closest_prompt(d.prompts, target_answer)
        d.target_text = target_answer
        d.heart_screen, d.heart = _heart_for_prompt(screens, per_screen, "", target_answer)
        if d.heart is None and d.target_prompt_index is not None:
            pr = d.prompts[d.target_prompt_index]
            d.heart_screen, d.heart = _heart_for_prompt(screens, per_screen, pr["title"], pr["answer"])
            d.target_text = pr["answer"]
        if d.heart is None:
            d.like = False
            d.reason += f" [could not find the like button for answer '{target_answer[:40]}'; not tapping blind]"
    elif d.like and not d.prompts:
        # photo-only profile: one vision call, button = first card's heart
        first = next(((s.index, s.hearts[0]) for s in screens if s.hearts), None)
        pd = ask_json(PHOTO_SYSTEM, [("Screenshot", downscale_jpeg(screens[0].image, C.IMAGE_WIDTH))],
                      "Write the comment.", PHOTO_SCHEMA, max_tokens=120)
        if first and pd and pd.get("comment"):
            d.heart_screen, d.heart = first
            d.comment = pd["comment"]; d.target_prompt_index = None
        else:
            d.like = False; d.reason += " [photo-only profile and no usable photo comment]"
    elif d.like:
        d.like = False; d.reason += " [model did not say which answer the comment is about]"
    return d


def _closest_prompt(prompts: list, answer: str) -> int | None:
    if not prompts:
        return None
    scores = [max(ocr.similar(p["answer"], answer), ocr.similar(p["title"], answer)) for p in prompts]
    return max(range(len(prompts)), key=lambda i: scores[i])


def heart_below_text(img, hearts, text: str):
    """On a fresh screenshot, find the like button of the card containing `text`."""
    for ln in ocr.read(img):
        if _line_matches(ln, "", text):
            below = [h for h in hearts if h[1] > ln.cy + 60]
            if below:
                return below[0]
    return None


def text_on_screen(img, text: str) -> bool:
    return any(_line_matches(ln, "", text) for ln in ocr.read(img, keep_all=True))


def _line_matches(ln, title: str, answer: str) -> bool:
    if title and ocr.similar(ln.text, title) >= 0.75:
        return True
    a, l = ocr.norm(answer), ocr.norm(ln.text)
    if len(l) < 8:
        return False
    return l in a or ocr.similar(a[:len(l)], l) >= 0.8


def _heart_for_prompt(screens, per_screen, title: str, answer: str):
    """The card's like button is the first detected heart below a line of
    the prompt (title or answer text), on that screen or the next one."""
    for j, lines in enumerate(per_screen):
        for ln in lines:
            if _line_matches(ln, title, answer):
                below = [h for h in screens[j].hearts if h[1] > ln.cy + 60]
                if below:
                    return j, below[0]
    for j, lines in enumerate(per_screen):
        if any(_line_matches(ln, title, answer) for ln in lines) and j + 1 < len(screens) and screens[j + 1].hearts:
            return j + 1, screens[j + 1].hearts[0]
    return None, None
