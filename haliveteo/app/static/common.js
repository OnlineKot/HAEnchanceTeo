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

HL.ON = new Set(["on","open","playing","unlocked","home","heat","cool","active","armed_home","armed_away","buffering"]);
HL.isOn = st => !!st && HL.ON.has(st.s);
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

// Build one tile. handlers: {press(tile, el), slide(tile, value, el)}. el.update(state) refreshes it live.
HL.makeTile = function(tile, handlers){
  const el = document.createElement("div");
  el.className = "tile t-" + tile.type + (tile.width === 2 ? " w2" : "");
  el.dataset.id = tile.id;
  if(tile.color) el.style.setProperty("--tc", tile.color);
  const icon = tile.icon || ({button:"▶️",toggle:"💡",slider:"🎚️",state:"📊"}[tile.type]);
  el.innerHTML = `<div class="ti">${HL.esc(icon)}</div><div><div class="tl">${HL.esc(tile.label || tile.entity_id || "")}</div><div class="ts"></div></div>`;
  const ts = el.querySelector(".ts");
  const ask = () => !tile.confirm || confirm((tile.label || "") + "?");
  if(tile.type === "button" || tile.type === "toggle"){
    el.onclick = () => { if(ask()) handlers.press(tile, el); };
    if(tile.type === "button") ts.textContent = ({service:tile.action.service,script:"script",scene:"scene",event:tile.action.event_type}[tile.action.kind]) || "";
  }
  let range, tv;
  if(tile.type === "slider"){
    range = document.createElement("input"); range.type = "range"; range.min = tile.min; range.max = tile.max; range.step = tile.step;
    range.oninput = () => { ts.textContent = range.value + (tile.mode === "number" ? "" : "%"); range.dragging = true; };
    range.onchange = () => { range.dragging = false; if(ask()) handlers.slide(tile, +range.value, el); };
    el.append(range);
  }
  if(tile.type === "state"){ tv = document.createElement("div"); tv.className = "tv"; el.insertBefore(tv, el.lastChild); }
  el.update = st => {
    el.classList.toggle("unavail", !st || st.s === "unavailable");
    if(tile.type === "toggle"){ el.classList.toggle("on", HL.isOn(st)); ts.textContent = st ? st.s : "—"; }
    else if(tile.type === "slider"){ const v = HL.sliderValue(tile, st);
      if(v != null && !range.dragging){ range.value = v; ts.textContent = v + (tile.mode === "number" ? "" : "%"); el.classList.toggle("on", v > tile.min); } }
    else if(tile.type === "state"){ tv.textContent = HL.stateText(tile, st) + (tile.unit ? " " + tile.unit : ""); ts.textContent = ""; }
  };
  if(tile.type !== "button") el.update(null);
  return el;
};

HL.renderGrid = function(box, layout, states, handlers){
  box.innerHTML = ""; box.style.setProperty("--cols", layout.cols || 2);
  const els = {};
  (layout.tiles || []).forEach(t => {
    const el = HL.makeTile(t, handlers); box.append(el);
    const eid = t.type === "button" ? "" : t.entity_id;
    if(eid){ (els[eid] = els[eid] || []).push([t, el]); el.update(states[eid]); }
  });
  return els;
};
HL.flash = (el, ok) => { if(!el) return; el.classList.remove("pulse","bad"); void el.offsetWidth; el.classList.add(ok ? "pulse" : "bad"); };
HL.time = ts => new Date(ts * 1000).toLocaleTimeString();
