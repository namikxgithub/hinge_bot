"""Local review page. The bot enqueues a draft and blocks until you tick
Send or Skip here. Nothing is sent that you did not approve."""
import json, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse


class Queue:
    def __init__(self, path: Path):
        self.path = path; self.lock = threading.Lock(); self.items: list[dict] = []
        if path.exists():
            self.items = json.loads(path.read_text())

    def _save(self):
        tmp = self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(self.items, indent=1)); tmp.replace(self.path)

    def add(self, item: dict):
        with self.lock:
            self.items.insert(0, item); self._save()

    def update(self, id_: str, **fields):
        with self.lock:
            for it in self.items:
                if it["id"] == id_:
                    it.update(fields); break
            self._save()

    def get(self, id_: str) -> dict | None:
        with self.lock:
            return next((dict(it) for it in self.items if it["id"] == id_), None)

    def wait_for_decision(self, id_: str, poll=2.0) -> dict:
        while True:
            it = self.get(id_)
            if it and it["status"] in ("approved", "skipped"):
                return it
            time.sleep(poll)

    def snapshot(self) -> list[dict]:
        with self.lock:
            return [dict(it) for it in self.items]


HTML = """<!doctype html><meta charset=utf-8><title>Hinge drafts</title>
<style>
body{font:15px/1.4 system-ui;margin:0;background:#f4f4f6;color:#111}
header{padding:12px 20px;background:#fff;border-bottom:1px solid #ddd;display:flex;gap:16px;align-items:center}
.card{background:#fff;margin:16px 20px;padding:16px;border-radius:10px;box-shadow:0 1px 3px #0002;border-left:6px solid #bbb}
.card.pending{border-left-color:#e0a800}.card.sent{border-left-color:#2e9e44}.card.failed{border-left-color:#c0392b}.card.skipped,.card.auto_skipped{border-left-color:#999}
.shots{display:flex;gap:8px;overflow-x:auto;padding:6px 0}.shots img{height:360px;border-radius:6px;border:1px solid #ddd}
textarea{width:100%;min-height:70px;font:inherit;padding:8px;box-sizing:border-box}
button{font:inherit;padding:8px 16px;border-radius:6px;border:1px solid #888;background:#fff;cursor:pointer}
button.send{background:#2e9e44;color:#fff;border-color:#2e9e44}
.meta{color:#555;font-size:13px}.tag{padding:2px 8px;border-radius:10px;background:#eee;font-size:12px}
.prompt{background:#fafafa;border:1px solid #eee;border-radius:6px;padding:8px;margin:6px 0}.prompt.target{border-color:#e0a800;background:#fff8e1}
</style>
<header><b>Hinge drafts</b><span id=status class=meta>loading</span></header>
<div id=list></div>
<script>
let acted=new Set();
function esc(s){return (s??'').toString().replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function load(){
  const items=await (await fetch('/queue.json',{cache:'no-store'})).json();
  const pending=items.filter(i=>i.status==='pending').length;
  document.getElementById('status').textContent=`${items.length} profiles, ${pending} waiting for you`;
  document.title=(pending?`(${pending}) `:'')+'Hinge drafts';
  const list=document.getElementById('list');
  for(const it of items){
    let el=document.getElementById('c-'+it.id);
    if(el&&el.dataset.status===it.status) continue;
    if(el&&it.status==='pending') continue; // don't clobber an edit in progress
    const html=render(it);
    if(el){el.outerHTML=html}else{list.insertAdjacentHTML(items.indexOf(it)===0?'afterbegin':'beforeend',html)}
  }
}
function render(it){
  const shots=(it.screenshots||[]).map(s=>`<img src="/shots/${s}">`).join('');
  const prompts=(it.prompts||[]).map((p,i)=>`<div class="prompt ${i===it.target_prompt_index?'target':''}"><b>${esc(p.title)}</b><br>${esc(p.answer)}</div>`).join('');
  let action='';
  if(it.status==='pending'){
    action=`<p><b>Draft comment</b> (edit freely):</p><textarea id="t-${it.id}">${esc(it.comment)}</textarea>
    <p><button class=send onclick="act('${it.id}','approve')">Send like with this comment</button>
    <button onclick="act('${it.id}','skip')">Skip this profile</button></p>`;
  } else if(it.final_comment||it.comment){
    action=`<p class=meta>Comment: ${esc(it.final_comment||it.comment)}</p>`;
  }
  return `<div class="card ${it.status}" id="c-${it.id}" data-status="${it.status}">
   <div><span class=tag>${esc(it.status)}</span> <b>${esc(it.name)}</b>${it.age?', '+it.age:''} <span class=meta>${esc(it.basics)}</span> <span class=meta>${esc(it.ts)}</span></div>
   <div class=shots>${shots}</div>
   <p class=meta>Model: ${it.like?'LIKE':'skip'} - ${esc(it.reason)}</p>
   ${prompts}${action}${it.error?`<p class=meta style="color:#c0392b">${esc(it.error)}</p>`:''}
  </div>`;
}
async function act(id,action){
  const t=document.getElementById('t-'+id); const comment=t?t.value:'';
  if(action==='approve'&&!comment.trim()){alert('Comment is empty');return}
  await fetch('/decide',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({id,action,comment})});
  load();
}
load();setInterval(load,3000);
</script>"""


def make_handler(queue: Queue, shots_dir: Path):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def _send(self, code, body: bytes, ctype="text/html; charset=utf-8"):
            self.send_response(code); self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            p = urlparse(self.path).path
            if p == "/":
                self._send(200, HTML.encode())
            elif p == "/queue.json":
                self._send(200, json.dumps(queue.snapshot()).encode(), "application/json")
            elif p.startswith("/shots/"):
                f = (shots_dir / p[len("/shots/"):]).resolve()
                if shots_dir.resolve() in f.parents and f.is_file():
                    self._send(200, f.read_bytes(), "image/png")
                else:
                    self._send(404, b"not found")
            else:
                self._send(404, b"not found")

        def do_POST(self):
            if urlparse(self.path).path != "/decide":
                return self._send(404, b"not found")
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0)) or 0) or b"{}")
            it = queue.get(body.get("id", ""))
            if not it or it["status"] != "pending":
                return self._send(409, b"not pending", "text/plain")
            if body.get("action") == "approve":
                queue.update(it["id"], status="approved", final_comment=body.get("comment", "").strip())
            else:
                queue.update(it["id"], status="skipped")
            self._send(200, b"ok", "text/plain")
    return H


def serve_in_thread(queue: Queue, shots_dir: Path, port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(queue, shots_dir))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
