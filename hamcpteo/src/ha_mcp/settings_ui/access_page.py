"""Access page (HAMcpTeo / TeodorTeo.com): colour-coded per-category levels."""

from __future__ import annotations

import json
import logging

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from .. import access_control

logger = logging.getLogger(__name__)

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HAMcpTeo - Access</title>
<style>
:root{--bg:#f4f5f7;--card:#fff;--fg:#1c1e21;--mut:#6b7280;--bd:#e3e5e8}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--card:#1b1e25;--fg:#e8eaed;--mut:#9aa0a6;--bd:#2c3038}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:16px}
h1{font-size:1.3rem;margin:4px 0}p.sub{color:var(--mut);margin:0 0 14px}
a{color:inherit}
.master{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:14px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--bd);border-left:6px solid var(--c);border-radius:14px;
 padding:12px 14px;margin-bottom:10px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.card .t{flex:1 1 220px;min-width:0}.card .n{font-weight:600}.card .h{color:var(--mut);font-size:.85rem}
.seg{display:flex;border:1px solid var(--bd);border-radius:10px;overflow:hidden}
.seg button{border:0;background:transparent;color:var(--fg);padding:9px 14px;font:inherit;cursor:pointer;min-width:74px}
.seg button+button{border-left:1px solid var(--bd)}
.seg button.on{background:var(--c,#555);color:#fff;font-weight:600}
.seg button.on.g{background:#546e7a}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.row .t{flex:1 1 220px;font-weight:600}
#toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:#263238;color:#fff;
 padding:9px 16px;border-radius:20px;opacity:0;transition:.25s;pointer-events:none}#toast.show{opacity:1}
footer{color:var(--mut);font-size:.8rem;text-align:center;margin:18px 0}
</style></head><body><div class="wrap">
<h1 id="h1"></h1><p class="sub" id="sub"></p>
<div class="master"><div class="row"><div class="t" id="mt"></div><div class="seg" id="mseg"></div></div></div>
<div id="list"></div>
<footer><a href="https://teodorteo.com" target="_blank" rel="noopener noreferrer">TeodorTeo.com</a> · <a href="./settings" id="back"></a></footer>
</div><div id="toast"></div>
<script>
const PL=(navigator.language||'').toLowerCase().startsWith('pl');
const T=PL?{h:'Dostęp dla AI',sub:'Wybierz, co AI może zobaczyć i zmieniać. Zmiany działają od razu.',
 master:'Wszystko naraz',none:'Brak',read:'Odczyt',full:'Pełny',saved:'Zapisano',err:'Błąd zapisu',back:'Ustawienia narzędzi'}
 :{h:'AI access',sub:'Choose what the AI may see and change. Changes apply immediately.',
 master:'Everything at once',none:'None',read:'Read',full:'Full',saved:'Saved',err:'Save failed',back:'Tool settings'};
const $=id=>document.getElementById(id);
$('h1').textContent=T.h;$('sub').textContent=T.sub;$('mt').textContent=T.master;$('back').textContent=T.back;
let cats=[],levels={};
function toast(m){const t=$('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1400)}
function seg(el,cur,color,on){el.innerHTML='';['none','read','full'].forEach(l=>{
 const b=document.createElement('button');b.textContent=T[l];
 if(cur===l){b.className='on'+(color?'':' g')}
 if(color)b.style.setProperty('--c',color);
 b.onclick=()=>on(l);el.appendChild(b)})}
async function save(patch){
 try{const r=await fetch('./api/access',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({levels:patch})});
  if(!r.ok)throw 0;levels=(await r.json()).levels;render();toast(T.saved)}catch(e){toast(T.err)}}
function render(){
 const vals=cats.map(c=>levels[c.id]);const all=vals.every(v=>v===vals[0])?vals[0]:null;
 seg($('mseg'),all,null,l=>save(Object.fromEntries(cats.map(c=>[c.id,l]))));
 const list=$('list');list.innerHTML='';
 cats.forEach(c=>{const d=document.createElement('div');d.className='card';d.style.setProperty('--c',c.color);
  d.innerHTML='<div class="t"><div class="n"></div><div class="h"></div></div><div class="seg"></div>';
  d.querySelector('.n').textContent=PL?c.pl:c.en;d.querySelector('.h').textContent=PL?c.hint_pl:c.hint_en;
  seg(d.querySelector('.seg'),levels[c.id],c.color,l=>save({[c.id]:l}));list.appendChild(d)})}
fetch('./api/access').then(r=>r.json()).then(d=>{cats=d.categories;levels=d.levels;render()}).catch(()=>toast(T.err));
</script></body></html>"""


async def access_page(_: Request) -> HTMLResponse:
    return HTMLResponse(_PAGE)


async def get_access(_: Request) -> JSONResponse:
    return JSONResponse(
        {"categories": access_control.catalog(), "levels": access_control.load_levels()}
    )


async def save_access(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        patch = body["levels"]
        if not isinstance(patch, dict):
            raise ValueError
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"error": "body must be {\"levels\": {...}}"}, status_code=400)
    try:
        levels = access_control.save_levels(patch)
    except OSError as err:
        logger.error("could not save access levels: %s", err)
        return JSONResponse({"error": "could not save"}, status_code=500)
    return JSONResponse({"levels": levels})
