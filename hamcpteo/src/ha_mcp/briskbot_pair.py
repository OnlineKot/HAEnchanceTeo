"""Sparuj z BriskBot (TeodorTeo.com): connect this add-on to BriskBot with a 6-character code.

In BriskBot (Ustawienia -> Dodatki -> Home Assistant -> Sparuj z HAMcpTeo) you get a code valid 10 minutes. On this
page (the add-on's "Open Web UI" -> Sparuj z BriskBot) you type it; the add-on then sends BriskBot its private MCP
address (public address + secret path) over HTTPS, and BriskBot adds it as an add-on for your bots. Nothing else is
sent. The page is reachable only through Home Assistant ingress (the Supervisor), like the rest of the settings UI.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

BRISKBOT = os.environ.get("BRISKBOT_URL", "https://briskbot.teodorteo.com")

_PAGE = """<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sparuj z BriskBot</title>
<style>
:root{color-scheme:light dark;--bg:#fff;--fg:#0d0d0d;--muted:#6b6b70;--line:#e5e5ea;--green:#2ec04f}
@media (prefers-color-scheme:dark){:root{--bg:#000;--fg:#f2f2f2;--muted:#8e8e93;--line:#2c2c2e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:460px;margin:0 auto;padding:40px 22px;animation:in .6s cubic-bezier(.2,.8,.2,1) both}
@keyframes in{from{opacity:0;filter:blur(10px);transform:translateY(6px)}to{opacity:1;filter:none;transform:none}}
h1{font-size:26px;margin:18px 0 6px}p{margin:0 0 14px;color:var(--muted)}
.mark{width:56px;height:56px}
form{display:flex;gap:8px;margin:22px 0 10px}
input{flex:1;min-width:0;height:48px;padding:0 16px;border-radius:999px;border:1px solid var(--line);background:transparent;color:var(--fg);font:600 20px/1 ui-monospace,Menlo,monospace;letter-spacing:.18em;text-transform:uppercase}
input::placeholder{letter-spacing:normal;font-weight:400;text-transform:none;font-family:inherit;font-size:16px}
button{height:48px;padding:0 22px;border-radius:999px;border:0;background:var(--fg);color:var(--bg);font:600 16px/1 inherit;cursor:pointer}
button:disabled{opacity:.4}
#msg{min-height:24px;margin-top:6px;animation:in .4s both}.ok{color:var(--green)!important}.bad{color:#ff453a!important}
ol{padding-left:20px;color:var(--muted);margin:24px 0 0}li{margin:0 0 6px}
</style></head><body><main>
<svg class="mark" viewBox="0 0 48 48" aria-hidden="true"><path d="M24 3C9 3 3 9 3 24s6 21 21 21 21-6 21-21S39 3 24 3z" fill="currentColor"/>
<g transform="rotate(-8 24 20)" fill="Canvas"><rect x="16" y="13" width="5" height="12" rx="2.5"/><rect x="27" y="13" width="5" height="12" rx="2.5"/></g>
<path d="M15 29.5l6.2 6.2L39 17" fill="none" stroke="#2ec04f" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>
<h1>Sparuj z BriskBot</h1>
<p>Wpisz kod z BriskBota, a Twoje boty dostaną ten Home Assistant.</p>
<form id="f"><input id="c" maxlength="9" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="Kod, np. K7Q2MX" aria-label="Kod z BriskBota"><button id="b">Sparuj</button></form>
<div id="msg" aria-live="polite"></div>
<ol><li>W BriskBocie: Ustawienia, Dodatki, Home Assistant, Sparuj z HAMcpTeo.</li><li>Przepisz tutaj kod (działa 10 minut).</li><li>Dodatek potrzebuje publicznego adresu https: public_url w konfiguracji albo External URL w Home Assistancie.</li></ol>
</main><script>
const f=document.getElementById('f'),c=document.getElementById('c'),b=document.getElementById('b'),m=document.getElementById('msg');
f.onsubmit=async(e)=>{e.preventDefault();b.disabled=true;m.className='';m.textContent='Łączę…';
try{const r=await fetch('briskbot/pair',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({code:c.value})});const j=await r.json();
m.textContent=j.message||'Coś poszło nie tak.';m.className=j.ok?'ok':'bad';}catch(err){m.textContent='Brak połączenia.';m.className='bad';}b.disabled=false;};
</script></body></html>"""


def register_briskbot_routes(mcp, guard, secret_path: str, public_url: str) -> None:
    """Mount GET /briskbot (the page) and POST /briskbot/pair, both only for HA ingress (``guard``)."""

    async def page(request: Request) -> HTMLResponse:
        return HTMLResponse(_PAGE)

    async def pair(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        code = "".join(ch for ch in str(body.get("code", "")).upper() if ch.isalnum())
        if len(code) != 6:
            return JSONResponse({"ok": False, "message": "Kod ma 6 znaków."})
        if not public_url:
            return JSONResponse({"ok": False, "message": "Dodatek nie zna swojego publicznego adresu. Ustaw public_url w konfiguracji dodatku (np. ha.twojadomena.pl) albo External URL w Home Assistancie i uruchom dodatek ponownie."})
        data = json.dumps({"code": code, "url": public_url.rstrip("/") + secret_path, "name": "Home Assistant"}).encode()
        req = urllib.request.Request(f"{BRISKBOT}/api/hamcp/pair", data=data, method="POST", headers={"content-type": "application/json", "user-agent": "HAMcpTeo"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                out = json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as err:
            try:
                out = json.loads(err.read() or b"{}")
            except ValueError:
                out = {"ok": False, "message": f"BriskBot odpowiedział błędem {err.code}."}
        except (OSError, ValueError) as err:
            out = {"ok": False, "message": f"Nie udało się połączyć z BriskBotem: {err}"}
        return JSONResponse({"ok": bool(out.get("ok")), "message": str(out.get("message", ""))[:400]})

    mcp.custom_route("/briskbot", methods=["GET"])(guard(page))
    mcp.custom_route("/briskbot/pair", methods=["POST"])(guard(pair))
