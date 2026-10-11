// Shared front-end helpers - by TeodorTeo.com (https://teodorteo.com)
const HL = {};
HL.esc = x => String(x ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
HL.lang = (navigator.language || "en").toLowerCase().startsWith("pl") ? "pl" : "en";
HL.tr = (pl, en) => HL.lang === "pl" ? pl : en;
HL.icon = name => { const d = HL.MDI && HL.MDI[String(name || "").replace(/^mdi:/, "")]; return d ? `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>` : (String(name || "").startsWith("mdi:") ? "" : HL.esc(name || "")); };
HL.ago = ts => { const s = Math.max(0, Date.now()/1000 - ts); if(s < 90) return HL.tr("przed chwilą","just now"); const m = s/60; if(m < 90) return Math.round(m) + " min"; const h = m/60; if(h < 48) return Math.round(h) + " h"; return Math.round(h/24) + " " + HL.tr("dni","days"); };
HL.api = async (p, o = {}) => { const r = await fetch("api/" + p, {...o, headers:{"Content-Type":"application/json"}}); const j = await r.json().catch(() => ({})); if(!r.ok) throw new Error(j.error || r.statusText); return j; };
HL.post = (p, b) => HL.api(p, {method:"POST", body:JSON.stringify(b ?? {})});
let _tt; HL.toast = (m, bad) => { let e = document.getElementById("toast"); if(!e){ e = document.createElement("div"); e.id = "toast"; document.body.append(e); }
  e.textContent = m; e.className = "toast on" + (bad ? " bad" : ""); clearTimeout(_tt); _tt = setTimeout(() => e.classList.remove("on"), 3200); };
HL.copyRow = (label, value) => { const w = document.createElement("div"); w.innerHTML = `<label class="f"></label><div style="display:flex;gap:6px"><input type="text" readonly style="flex:1"><button class="b alt sm">${HL.tr("Kopiuj","Copy")}</button></div>`;
  w.querySelector("label").textContent = label; const i = w.querySelector("input"); i.value = value;
  w.querySelector("button").onclick = async () => { try{ await navigator.clipboard.writeText(value); }catch{ i.select(); document.execCommand("copy"); } HL.toast(HL.tr("Skopiowano ✓","Copied ✓")); }; return w; };
