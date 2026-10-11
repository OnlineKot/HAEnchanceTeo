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
HL.copyRow = (label, value) => { const w = document.createElement("div"); w.innerHTML = `<label class="f"></label><div class="copy"><input type="text" readonly><button class="b alt sm">${HL.tr("Kopiuj","Copy")}</button></div>`;
  w.querySelector("label").textContent = label; const i = w.querySelector("input"); i.value = value;
  w.querySelector("button").onclick = async () => { try{ await navigator.clipboard.writeText(value); }catch{ i.select(); document.execCommand("copy"); } HL.toast(HL.tr("Skopiowano ✓","Copied ✓")); }; return w; };
// Overflow menu: HL.kebab([[action, label, className, disabled], ...]) -> <details class="kb"> whose buttons carry data-a.
HL.kebab = items => {
  const d = document.createElement("details"); d.className = "kb";
  d.innerHTML = `<summary aria-label="${HL.tr("Więcej","More")}">${HL.icon("mdi:dots-vertical")}</summary><div></div>`;
  items.forEach(([a, label, cls, off]) => { const b = document.createElement("button"); b.type = "button"; b.dataset.a = a; b.textContent = label; if(cls) b.className = cls; if(off) b.disabled = true; d.lastChild.append(b); });
  return d;
};
document.addEventListener("click", e => document.querySelectorAll("details.kb[open]").forEach(d => { if(!d.contains(e.target) || e.target.closest("[data-a]")) d.open = false; }));
// Keyed list sync: only rows whose data changed are rebuilt, open <details> inside them stay open, nothing else is touched (no flicker, no jumps).
HL.sync = (box, items, key, make, sig) => {
  const old = new Map([...box.children].map(c => [c.dataset.k, c])); let prev = null;
  items.forEach(it => {
    const k = String(key(it)), s = sig ? sig(it) : JSON.stringify(it); let el = old.get(k); old.delete(k);
    if(!el || el._sig !== s){
      const fresh = make(it); fresh.dataset.k = k; fresh._sig = s;
      if(el){ const was = [...el.querySelectorAll("details")].map(x => x.open); fresh.querySelectorAll("details").forEach((x, i) => { if(was[i]) x.open = true; }); el.replaceWith(fresh); }
      el = fresh;
    }
    const want = prev ? prev.nextSibling : box.firstChild;
    if(el !== want) box.insertBefore(el, want);
    prev = el; });
  old.forEach(el => el.remove());
};
