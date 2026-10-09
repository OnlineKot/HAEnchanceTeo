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
HL.DOMAIN_COLOR = {light:"#ffc107",switch:"#ffc107",input_boolean:"#ffc107",fan:"#00bcd4",cover:"#926bc7",lock:"#4caf50",media_player:"#03a9f4",climate:"#ff6f22",humidifier:"#2196f3",vacuum:"#009688",siren:"#f44336",alarm_control_panel:"#4caf50"};
HL.DEFAULT_ICON = {light:"lightbulb",switch:"toggle-switch",input_boolean:"toggle-switch",fan:"fan",cover:"blinds",lock:"lock",media_player:"speaker",climate:"thermostat",scene:"palette",script:"script-text-play",sensor:"eye",binary_sensor:"eye",input_number:"tune-variant",number:"tune-variant",button:"gesture-tap",slider:"tune-variant",state:"eye",toggle:"toggle-switch",event:"bullhorn-outline",live:"lightning-bolt-circle"};
// Icon: "mdi:name" -> bundled Material Design Icon (same set as Home Assistant); anything else (emoji) is shown as text.
HL.icon = name => {
  const n = String(name || "").replace(/^mdi:/, "");
  const d = HL.MDI && HL.MDI[n];
  return d ? `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>` : HL.esc(name || "");
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
  const dom = (tile.entity_id || "").split(".")[0];
  el.style.setProperty("--tc", tile.color || HL.DOMAIN_COLOR[dom] || "var(--primary-color)");
  el.innerHTML = `<div class="trow"><div class="tshape">${HL.icon(HL.tileIcon(tile))}</div><div class="tinfo"><div class="tn"></div><div class="tst"></div></div></div>`;
  el.querySelector(".tn").textContent = tile.label || tile.entity_id || (tile.action && tile.action.entity_id) || "";
  const tst = el.querySelector(".tst"), ask = () => !tile.confirm || confirm((tile.label || "") + "?");
  let range, fill, thumb, hs, longTimer, longFired = false;
  const show = v => { const p = (v - tile.min) / (tile.max - tile.min) * 100; fill.style.width = p + "%"; thumb.style.left = p + "%"; };
  if(tile.type === "button" || tile.type === "toggle"){
    el.onclick = () => { if(longFired){ longFired = false; return; } if(ask()) handlers.press(tile, el); };
    tst.textContent = HL.tileSub(tile);
  }
  if(tile.type === "slider"){
    const f = document.createElement("div"); f.className = "tfeat";
    f.innerHTML = `<div class="hs"><div class="hs-fill"></div><div class="hs-thumb"></div><input type="range"></div>`;
    el.append(f); hs = f.querySelector(".hs"); fill = f.querySelector(".hs-fill"); thumb = f.querySelector(".hs-thumb"); range = f.querySelector("input");
    range.min = tile.min; range.max = tile.max; range.step = tile.step;
    range.oninput = () => { hs.classList.add("drag"); range.dragging = true; show(+range.value); tst.textContent = range.value + (tile.mode === "number" ? "" : "%"); };
    range.onchange = () => { hs.classList.remove("drag"); range.dragging = false; if(ask()) handlers.slide(tile, +range.value, el); };
  }
  if(handlers.info && tile.type !== "button"){   // long press = more-info dialog
    el.addEventListener("pointerdown", () => { longFired = false; longTimer = setTimeout(() => { longFired = true; handlers.info(tile); }, 550); });
    ["pointerup","pointerleave","pointercancel"].forEach(ev => el.addEventListener(ev, () => clearTimeout(longTimer)));
    el.addEventListener("contextmenu", e => { e.preventDefault(); handlers.info(tile); });
  }
  el.update = st => {
    el.classList.toggle("unavail", !!st && st.s === "unavailable");
    if(tile.type === "toggle"){ el.classList.toggle("on", HL.isOn(tile, st)); tst.textContent = st ? st.s : "—"; }
    else if(tile.type === "slider"){ const v = HL.sliderValue(tile, st);
      if(v != null && !range.dragging){ range.value = v; show(v); tst.textContent = v + (tile.mode === "number" ? "" : "%"); el.classList.toggle("on", v > tile.min); } }
    else if(tile.type === "state"){ tst.textContent = HL.stateText(tile, st) + (tile.unit ? " " + tile.unit : ""); }
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
// HA-style "more info" dialog for a tile's entity
HL.moreInfo = function(tile, st){
  const d = document.createElement("dialog"); d.className = "hd";
  const attrs = Object.entries((st && st.a) || {}).filter(([k]) => !["friendly_name","icon","entity_picture","supported_features","supported_color_modes"].includes(k));
  d.innerHTML = `<div class="hd-card"><h2></h2><div class="hint"></div><div style="font-size:28px;line-height:40px;margin:8px 0"></div>
    <div class="at"></div><div style="display:flex;justify-content:flex-end;margin-top:16px"><button class="b alt">${HL.tr("Zamknij","Close")}</button></div></div>`;
  d.querySelector("h2").textContent = (st && st.a && st.a.friendly_name) || tile.label || tile.entity_id;
  d.querySelector(".hint").textContent = tile.entity_id;
  d.querySelector("div[style]").textContent = st ? st.s : "—";
  d.querySelector(".at").innerHTML = attrs.map(([k, v]) => `<div style="display:flex;gap:12px;padding:6px 0;border-top:1px solid var(--divider-color)"><span class="hint" style="flex:0 0 40%;word-break:break-word">${HL.esc(k)}</span><span style="flex:1;word-break:break-word">${HL.esc(typeof v === "object" ? JSON.stringify(v) : v)}</span></div>`).join("");
  d.querySelector("button").onclick = () => d.close(); d.onclose = () => d.remove();
  document.body.append(d); d.showModal();
};
HL.flash = (el, ok) => { if(!el) return; el.classList.remove("pulse","bad"); void el.offsetWidth; el.classList.add(ok ? "pulse" : "bad"); };
HL.time = ts => new Date(ts * 1000).toLocaleTimeString();
