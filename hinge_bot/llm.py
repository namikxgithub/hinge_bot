"""Model backend. BACKEND in config selects "ollama" (free, local) or
"anthropic" (API, paid). Both take a system prompt, a list of JPEG images
with captions, and a JSON schema, and return the parsed object or None."""
import base64, json, urllib.request
from . import config as C


def ask_json(system: str, images: list[tuple[str, bytes]], question: str, schema: dict, max_tokens=2000) -> dict | None:
    if C.BACKEND == "ollama":
        return _ollama(system, images, question, schema, max_tokens)
    return _anthropic(system, images, question, schema, max_tokens)


# ---- Ollama ----
def _ollama(system, images, question, schema, max_tokens):
    text = "\n".join(cap for cap, _ in images) + "\n" + question
    body = {"model": C.OLLAMA_MODEL, "stream": False, "format": schema,
            "options": {"num_ctx": C.OLLAMA_NUM_CTX, "temperature": 0.3, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": text,
                          "images": [base64.standard_b64encode(b).decode() for _, b in images]}]}
    req = urllib.request.Request(C.OLLAMA_URL + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=C.OLLAMA_TIMEOUT) as r:
        out = json.loads(r.read())
    content = out["message"]["content"].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        return json.loads(content[start:end + 1]) if start >= 0 else None


def ollama_ready() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(C.OLLAMA_URL + "/api/tags", timeout=5) as r:
            names = [m["name"] for m in json.loads(r.read()).get("models", [])]
        if not any(n.startswith(C.OLLAMA_MODEL) for n in names):
            return False, f"model {C.OLLAMA_MODEL} not pulled; have {names}"
        return True, "ok"
    except Exception as e:
        return False, f"ollama not reachable at {C.OLLAMA_URL}: {e}"


# ---- Anthropic API ----
_client = None


def _anthropic(system, images, question, schema, max_tokens):
    import anthropic
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    content = []
    for cap, b in images:
        content.append({"type": "text", "text": cap})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": base64.standard_b64encode(b).decode()}})
    content.append({"type": "text", "text": question})
    kwargs = dict(model=C.MODEL, max_tokens=max_tokens, system=system,
                  messages=[{"role": "user", "content": content}],
                  output_config={"format": {"type": "json_schema", "schema": schema}})
    try:
        resp = _client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except anthropic.BadRequestError:
        resp = _client.messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        return None
    return json.loads(next((b.text for b in resp.content if b.type == "text"), "{}"))
