// HALiveTeo shared front-end - by TeodorTeo.com (https://teodorteo.com)
const HL = {};
HL.esc = x => String(x ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
HL.lang = (navigator.language || "en").toLowerCase().startsWith("pl") ? "pl" : "en";
HL.tr = (pl, en) => HL.lang === "pl" ? pl : en;

// Live WebSocket with automatic reconnect. Path is relative so it also works behind Home Assistant ingress.
HL.live = function(opts){
  let ws, retry = 0, closed = false, everOpen = false;
  const url = () => (location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host +
    location.pathname.replace(/[^/]*$/, "") + "ws" + (opts.query || "");
  function connect(){
    ws = new WebSocket(url());
    ws.onopen = () => { retry = 0; everOpen = true; opts.onStatus && opts.onStatus(true); };
    ws.onmessage = e => { try{ opts.onMsg(JSON.parse(e.data)); }catch(err){ console.error(err); } };
    ws.onclose = () => {
      opts.onStatus && opts.onStatus(false, everOpen, retry);
      if(!closed) setTimeout(connect, Math.min(10000, 500 * 2 ** Math.min(retry++, 5)));
    };
  }
  connect();
  return { send: o => { if(ws.readyState === 1){ ws.send(JSON.stringify(o)); return true; } return false; },
           close(){ closed = true; ws.close(); } };
};

HL.ON = new Set(["on","open","playing","unlocked","home","heat","cool","active","armed_home","armed_away","buffering","locked"]);
HL.isOn = (tile, st) => !!st && (tile.entity_id.startsWith("lock.") ? st.s === "locked" : HL.ON.has(st.s));
HL.DEFAULT_ICON = {light:"lightbulb",switch:"toggle-switch",input_boolean:"toggle-switch",fan:"fan",cover:"blinds",lock:"lock",media_player:"speaker",climate:"thermostat",scene:"palette",script:"script-text-play",sensor:"eye",binary_sensor:"eye",input_number:"tune-variant",number:"tune-variant",button:"gesture-tap",slider:"tune-variant",state:"eye",toggle:"toggle-switch",event:"bullhorn-outline",live:"lightning-bolt-circle"};
// Icon: "mdi:name" -> bundled Material Design Icon (same set as Home Assistant); anything else (emoji) is shown as text.
HL.icon = name => {
  const n = String(name || "").replace(/^mdi:/, "");
  const d = HL.MDI && HL.MDI[n];
  return d ? `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>` : (String(name || "").startsWith("mdi:") ? "" : HL.esc(name || ""));
};
HL.tileIcon = tile => {
  if(tile.icon) return tile.icon;
  const dom = (tile.type === "button" ? ((tile.action.kind === "service" ? tile.action.service : tile.action.kind === "event" ? "event" : tile.action.kind === "live" ? "live" : tile.action.kind)) : tile.entity_id || "").split(".")[0];
  return "mdi:" + (HL.DEFAULT_ICON[dom] || HL.DEFAULT_ICON[tile.type] || "gesture-tap");
};
HL.sliderValue = (tile, st) => {
  if(!st) return null;
  const a = st.a || {};
  if(tile.mode === "light") return st.s === "on" ? Math.round((a.brightness ?? 255) / 255 * 100) : 0;
  if(tile.mode === "volume") return a.volume_level != null ? Math.round(a.volume_level * 100) : null;
  const v = parseFloat(st.s); return isNaN(v) ? null : v;
};
HL.stateText = (tile, st) => {
  if(!st) return "—";
  if(tile.type === "state" && tile.attribute) return String((st.a || {})[tile.attribute] ?? "—");
  return st.s;
};
HL.tileSub = tile => {
  if(tile.type !== "button") return "";
  const a = tile.action;
  return ({service:a.service, script:"script", scene:"scene", event:a.event_type, live:"Live Activity"})[a.kind] || "";
};

// Build one tile (Home Assistant "tile card" layout). handlers: {press, slide, info}. el.update(state) refreshes it live.
HL.makeTile = function(tile, handlers){
  const el = document.createElement("div");
  el.className = "tile t-" + tile.type + (tile.width === 2 ? " w2" : "");
  el.dataset.id = tile.id;
  if(tile.color) el.style.setProperty("--tc", tile.color);   // only an explicit tile colour overrides the single accent
  el.innerHTML = `<div class="trow"><div class="tshape">${HL.icon(HL.tileIcon(tile))}</div><div class="tinfo"><div class="tn"></div><div class="tst"></div></div></div>`;
  el.querySelector(".tn").textContent = tile.label || tile.entity_id || (tile.action && tile.action.entity_id) || "";
  const tst = el.querySelector(".tst"), ask = () => !tile.confirm || confirm((tile.label || "") + "?");
  let range, fill, thumb, hs, longTimer, longFired = false, lastSt = null, optTimer = 0, pendTimer = 0;
  const show = v => { const p = (v - tile.min) / (tile.max - tile.min) * 100; fill.style.width = p + "%"; thumb.style.left = p + "%"; };
  if(tile.type === "button" || tile.type === "toggle"){
    el.onclick = () => { if(longFired){ longFired = false; return; } if(!ask()) return;
      // instant feedback: pressed look now, toggles flip optimistically (the real state or the ack settles it)
      el.classList.add("pend"); clearTimeout(pendTimer); pendTimer = setTimeout(() => el.classList.remove("pend"), 8000);
      if(tile.type === "toggle"){ const on = !el.classList.contains("on"); el.classList.toggle("on", on); }
      handlers.press(tile, el); };
    tst.textContent = HL.tileSub(tile);
  }
  if(tile.type === "slider"){
    const f = document.createElement("div"); f.className = "tfeat";
    f.innerHTML = `<div class="hs"><div class="hs-fill"></div><div class="hs-thumb"></div><input type="range"></div>`;
    el.append(f); hs = f.querySelector(".hs"); fill = f.querySelector(".hs-fill"); thumb = f.querySelector(".hs-thumb"); range = f.querySelector("input");
    range.min = tile.min; range.max = tile.max; range.step = tile.step;
    range.oninput = () => { hs.classList.add("drag"); range.dragging = true; show(+range.value); tst.textContent = range.value + (tile.mode === "number" ? "" : "%"); };
    range.onchange = () => { hs.classList.remove("drag"); range.dragging = false; if(ask()){ el.classList.add("pend"); clearTimeout(pendTimer); pendTimer = setTimeout(() => el.classList.remove("pend"), 8000); handlers.slide(tile, +range.value, el); } else el.update(lastSt); };
  }
  if(handlers.info && tile.type !== "button"){   // long press = more-info dialog
    el.addEventListener("pointerdown", () => { longFired = false; longTimer = setTimeout(() => { longFired = true; handlers.info(tile); }, 550); });
    ["pointerup","pointerleave","pointercancel"].forEach(ev => el.addEventListener(ev, () => clearTimeout(longTimer)));
    el.addEventListener("contextmenu", e => { e.preventDefault(); handlers.info(tile); });
  }
  el.settle = ok => {   // request answered: failure rolls the optimistic state back at once, success waits a moment for the real state
    clearTimeout(pendTimer); el.classList.remove("pend"); clearTimeout(optTimer);
    if(tile.type === "button") return;
    optTimer = setTimeout(() => el.update(lastSt), ok ? 1500 : 0);
  };
  el.update = st => {
    lastSt = st; clearTimeout(optTimer);
    el.classList.toggle("unavail", !!st && st.s === "unavailable");
    if(tile.type === "toggle"){ el.classList.toggle("on", HL.isOn(tile, st)); tst.textContent = st ? st.s : "—"; }
    else if(tile.type === "slider"){ const v = HL.sliderValue(tile, st);
      if(v != null && !range.dragging){ range.value = v; show(v); tst.textContent = v + (tile.mode === "number" ? "" : "%"); el.classList.toggle("on", v > tile.min); } }
    else if(tile.type === "state"){ tst.textContent = HL.stateText(tile, st) + (tile.unit ? " " + tile.unit : ""); }
  };
  if(tile.type !== "button") el.update(null);
  return el;
};

// Renders the tile grid. If the layout did not change since the last call, only the live states are patched (no flicker, no jumps).
HL.renderGrid = function(box, layout, states, handlers){
  const sig = JSON.stringify(layout);
  if(box._sig === sig && box._els){ Object.entries(box._els).forEach(([eid, list]) => list.forEach(([t, el]) => el.update(states[eid]))); return box._els; }
  box.innerHTML = ""; box.style.setProperty("--cols", layout.cols || 2);
  const els = {}; box._sig = sig; box._els = els;
  (layout.tiles || []).forEach(t => {
    const el = HL.makeTile(t, handlers); box.append(el);
    const eid = t.type === "button" ? "" : t.entity_id;
    if(eid){ (els[eid] = els[eid] || []).push([t, el]); el.update(states[eid]); }
  });
  return els;
};
// HA-style "more info" dialog for a tile's entity
HL.moreInfo = function(tile, st){
  const d = document.createElement("dialog"); d.className = "hd";
  const attrs = Object.entries((st && st.a) || {}).filter(([k]) => !["friendly_name","icon","entity_picture","supported_features","supported_color_modes"].includes(k));
  d.innerHTML = `<div class="hd-card"><h2></h2><div class="hint"></div><div class="mi-v"></div>
    <div class="at"></div><div class="acts"><button class="b">${HL.tr("Zamknij","Close")}</button></div></div>`;
  d.querySelector("h2").textContent = (st && st.a && st.a.friendly_name) || tile.label || tile.entity_id;
  d.querySelector(".hint").textContent = tile.entity_id;
  d.querySelector(".mi-v").textContent = st ? st.s : "—";
  d.querySelector(".at").innerHTML = attrs.map(([k, v]) => `<div class="mi-r"><span class="hint">${HL.esc(k)}</span><span>${HL.esc(typeof v === "object" ? JSON.stringify(v) : v)}</span></div>`).join("");
  d.querySelector("button").onclick = () => d.close(); d.onclose = () => d.remove();
  document.body.append(d); d.showModal();
};
// Result of a request: brief static outline (no animation), optimistic state settled.
HL.flash = (el, ok) => { if(!el) return; clearTimeout(el._ft); el.classList.remove("ok","bad"); el.classList.add(ok ? "ok" : "bad");
  el._ft = setTimeout(() => el.classList.remove("ok","bad"), ok ? 500 : 1600); if(el.settle) el.settle(ok); };
// Overflow menu: HL.kebab([[action, label, className, disabled], ...]) -> <details class="kb"> whose buttons carry data-a.
HL.kebab = items => {
  const d = document.createElement("details"); d.className = "kb";
  d.innerHTML = `<summary aria-label="${HL.tr("Więcej","More")}">${HL.icon("mdi:dots-vertical")}</summary><div></div>`;
  items.forEach(([a, label, cls, off]) => { const b = document.createElement("button"); b.type = "button"; b.dataset.a = a; b.textContent = label; if(cls) b.className = cls; if(off) b.disabled = true; d.lastChild.append(b); });
  return d;
};
document.addEventListener("click", e => document.querySelectorAll("details.kb[open]").forEach(d => { if(!d.contains(e.target) || e.target.closest("[data-a]")) d.open = false; }));
// Keyed list sync: only rows whose data changed are rebuilt, open <details> inside them stay open, nothing else is touched.
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
HL.time = ts => new Date(ts * 1000).toLocaleTimeString();
