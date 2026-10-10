/* HACardsTeo - dependency-free Lovelace cards (teo-card, teo-chips, teo-title, teo-room, teo-media, teo-stats). By TeodorTeo.com (https://teodorteo.com) */
(() => {
"use strict";
if (window.__teoCards) return;
window.__teoCards = 1;
const VERSION = "1.0.1";
window.TEO_CARDS_VERSION = VERSION;

/* ---------- helpers ---------- */
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const dom = id => String(id || "").split(".")[0];
const fire = (n, t, d) => { const e = new Event(t, {bubbles: true, composed: true}); e.detail = d; n.dispatchEvent(e); return e; };
const num = v => { const n = parseFloat(v); return isNaN(n) ? null : n; };
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const arr = v => v == null ? [] : Array.isArray(v) ? v : [v];
const OFFS = ["off", "unavailable", "unknown", "none"];
const ENT = (c, ...k) => k.reduce((o, x) => (o && typeof o === "object" ? o[x] : undefined), c);
const COLORS = {red: "#f44336", pink: "#e91e63", purple: "#9c27b0", "deep-purple": "#673ab7", indigo: "#3f51b5", blue: "#2196f3", "light-blue": "#03a9f4", cyan: "#00bcd4", teal: "#009688", green: "#4caf50", "light-green": "#8bc34a", lime: "#cddc39", yellow: "#ffeb3b", amber: "#ffc107", orange: "#ff9800", "deep-orange": "#ff5722", brown: "#795548", "light-grey": "#bdbdbd", grey: "#9e9e9e", "dark-grey": "#616161", "blue-grey": "#607d8b", black: "#000", white: "#fff", disabled: "#9e9e9e"};
const COLOR_NAMES = Object.keys(COLORS);
const color = n => !n ? "" : /^(#|rgb|hsl|var\()/.test(n) ? n : n === "primary" ? "var(--primary-color,#03a9f4)" : n === "accent" ? "var(--accent-color,#ff9800)" : COLORS[n] ? `var(--${n}-color,${COLORS[n]})` : n;

/* ---------- i18n (en / pl; unknown states fall back to a prettified raw value) ---------- */
const L = {
en: {on: "On", off: "Off", open: "Open", close: "Close", closed: "Closed", opening: "Opening", closing: "Closing", locked: "Locked", unlocked: "Unlocked", locking: "Locking", unlocking: "Unlocking", jammed: "Jammed", home: "Home", not_home: "Away", playing: "Playing", paused: "Paused", idle: "Idle", standby: "Standby", cleaning: "Cleaning", docked: "Docked", returning: "Returning", error: "Error", heat: "Heat", cool: "Cool", heat_cool: "Heat/Cool", auto: "Auto", dry: "Dry", fan_only: "Fan", heating: "Heating", cooling: "Cooling", drying: "Drying", fan: "Fan", unavailable: "Unavailable", unknown: "Unknown", armed_home: "Armed home", armed_away: "Armed away", armed_night: "Armed night", disarmed: "Disarmed", pending: "Pending", triggered: "Triggered", arming: "Arming", active: "Active", update_available: "Update available", up_to_date: "Up to date", run: "Run", press: "Press", install: "Install", lock: "Lock", unlock: "Unlock", stop: "Stop", library: "Library", back: "Back", search: "Filter", speakers: "Speakers", source: "Source", nothing: "Nothing playing", morning: "Good morning", afternoon: "Good afternoon", evening: "Good evening", night: "Good night", lights_on: "lights on", all_off: "All off", all_on: "All on", people_home: "home", battery_low: "low battery", empty: "Empty", loading: "Loading...", failed: "Could not load", start: "Start", pause: "Pause", cancel: "Cancel", dock: "Dock", locate: "Locate", disarm: "Disarm", arm_home: "Home", arm_away: "Away", arm_night: "Night", code: "Code", more: "More", colors: "Colours", sunny: "Sunny", target: "Target", current: "Now", entity: "Entity", name: "Name", icon: "Icon", color: "Colour", layout: "Layout", graph: "Show 24h graph", tap_action: "Tap action", hold_action: "Hold action", double_tap_action: "Double-tap action", icon_tap_action: "Icon tap action", title: "Title", subtitle: "Subtitle", greeting: "Greeting by time of day", show_date: "Show date", align: "Alignment", area: "Area", entities: "Entities", temperature_entity: "Temperature entity", humidity_entity: "Humidity entity", buttons: "Button entities", speakers: "Speaker group", start_path: "Library start path", animate: "Animated icons", secondary_info: "Secondary info (attribute or last-changed)", columns: "Columns", decimals: "Decimals", chips_hint: "Per-chip options (type, icon, actions) are available in YAML.", inactive: "Idle", elapsed: "ago", now: "just now", camera: "Camera"},
pl: {on: "Wł.", off: "Wył.", open: "Otwarte", close: "Zamknij", closed: "Zamknięte", opening: "Otwieranie", closing: "Zamykanie", locked: "Zamknięty", unlocked: "Otwarty", locking: "Zamykanie", unlocking: "Otwieranie", jammed: "Zablokowany", home: "W domu", not_home: "Poza domem", playing: "Gra", paused: "Wstrzymano", idle: "Bezczynny", standby: "Czuwanie", cleaning: "Sprząta", docked: "W stacji", returning: "Wraca", error: "Błąd", heat: "Grzanie", cool: "Chłodzenie", heat_cool: "Grzanie/chłodz.", auto: "Auto", dry: "Osuszanie", fan_only: "Wentylator", heating: "Grzeje", cooling: "Chłodzi", drying: "Osusza", fan: "Wentylator", unavailable: "Niedostępny", unknown: "Nieznany", armed_home: "Uzbrojony dom", armed_away: "Uzbrojony poza domem", armed_night: "Uzbrojony noc", disarmed: "Rozbrojony", pending: "Oczekuje", triggered: "Alarm!", arming: "Uzbrajanie", active: "Aktywny", update_available: "Dostępna aktualizacja", up_to_date: "Aktualne", run: "Uruchom", press: "Naciśnij", install: "Instaluj", lock: "Zamknij", unlock: "Otwórz", stop: "Stop", library: "Biblioteka", back: "Wstecz", search: "Filtruj", speakers: "Głośniki", source: "Źródło", nothing: "Nic nie gra", morning: "Dzień dobry", afternoon: "Dzień dobry", evening: "Dobry wieczór", night: "Dobranoc", lights_on: "świateł wł.", all_off: "Wyłącz wszystko", all_on: "Włącz wszystko", people_home: "w domu", battery_low: "słaba bateria", empty: "Pusto", loading: "Ładowanie...", failed: "Nie udało się wczytać", start: "Start", pause: "Pauza", cancel: "Anuluj", dock: "Do stacji", locate: "Znajdź", disarm: "Rozbrój", arm_home: "Dom", arm_away: "Wyjście", arm_night: "Noc", code: "Kod", more: "Więcej", colors: "Kolory", sunny: "Słonecznie", target: "Cel", current: "Teraz", entity: "Encja", name: "Nazwa", icon: "Ikona", color: "Kolor", layout: "Układ", graph: "Wykres z 24 h", tap_action: "Akcja dotknięcia", hold_action: "Akcja przytrzymania", double_tap_action: "Akcja dwukrotnego dotknięcia", icon_tap_action: "Akcja ikony", title: "Tytuł", subtitle: "Podtytuł", greeting: "Powitanie zależne od pory dnia", show_date: "Pokaż datę", align: "Wyrównanie", area: "Obszar", entities: "Encje", temperature_entity: "Encja temperatury", humidity_entity: "Encja wilgotności", buttons: "Encje przycisków", speakers: "Grupa głośników", start_path: "Ścieżka startowa biblioteki", animate: "Animowane ikony", secondary_info: "Dodatkowa informacja (atrybut lub last-changed)", columns: "Kolumny", decimals: "Miejsca po przecinku", chips_hint: "Opcje pojedynczych chipów (typ, ikona, akcje) dostępne w YAML.", inactive: "Bezczynny", elapsed: "temu", now: "przed chwilą", camera: "Kamera"},
};
const lang = h => String((h && (h.locale && h.locale.language || h.language)) || "en").slice(0, 2);
const tr = (h, k) => (L[lang(h)] || L.en)[k] ?? L.en[k] ?? k;
const pretty = s => { s = String(s ?? "").replace(/_/g, " "); return s.charAt(0).toUpperCase() + s.slice(1); };
const sTxt = (h, st) => {
  if (!st) return "";
  const s = st.state, d = dom(st.entity_id), u = st.attributes.unit_of_measurement;
  if (h && h.formatEntityState) { try { return h.formatEntityState(st); } catch (e) { /* fall through */ } }
  if (u && num(s) != null) return `${s} ${u}`;
  const w = lang(h) === "pl" ? L.pl : L.en;
  if (d === "binary_sensor") return BIN(h, st.attributes.device_class, s);
  return w[s] ?? L.en[s] ?? pretty(s);
};
const BINMAP = {door: ["open", "closed"], window: ["open", "closed"], garage_door: ["open", "closed"], opening: ["open", "closed"], lock: ["unlocked", "locked"], motion: ["Motion", "Clear"], occupancy: ["Occupied", "Clear"], presence: ["home", "not_home"], smoke: ["Smoke", "Clear"], moisture: ["Wet", "Dry"], gas: ["Gas", "Clear"], problem: ["Problem", "OK"], battery: ["Low", "OK"], connectivity: ["Connected", "Disconnected"], plug: ["Plugged in", "Unplugged"], vibration: ["Vibration", "Clear"], tamper: ["Tampering", "Clear"], safety: ["Unsafe", "Safe"], running: ["Running", "Not running"], light: ["Light", "No light"], cold: ["Cold", "Normal"], heat: ["Hot", "Normal"], sound: ["Sound", "Clear"], carbon_monoxide: ["Detected", "Clear"]};
const BIN = (h, dc, s) => { const m = BINMAP[dc]; if (!m) return tr(h, s); const v = m[s === "on" ? 0 : 1]; return L.en[v] ? tr(h, v) : v; };

/* ---------- actions ---------- */
const haptic = t => fire(window, "haptic", t || "light");
function runAction(node, h, a, entity) {
  a = a || {};
  const act = a.action || "more-info";
  if (act === "none" || !h) return;
  haptic(act === "more-info" ? "light" : "medium");
  const id = a.entity || entity;
  if (act === "more-info") { if (id) fire(node, "hass-more-info", {entityId: id}); }
  else if (act === "toggle") { if (id) h.callService("homeassistant", "toggle", {entity_id: id}); }
  else if (act === "navigate") { if (a.navigation_path) { history.pushState(null, "", a.navigation_path); fire(window, "location-changed", {replace: !!a.navigation_replace}); } }
  else if (act === "url") { if (a.url_path) window.open(a.url_path, "_blank", "noopener"); }
  else if (act === "call-service" || act === "perform-action") {
    const s = String(a.perform_action || a.service || "").split(".");
    if (s.length === 2) h.callService(s[0], s[1], a.data || a.service_data || {}, a.target || (a.data && a.data.entity_id ? undefined : undefined));
  } else if (act === "fire-dom-event") fire(node, "ll-custom", a);
}

/* ---------- 24h history -> sparkline (fetched on demand, small capped cache) ---------- */
const HC = new Map(), HP = new Map();
function history(h, id) {
  const c = HC.get(id);
  if (c && Date.now() - c.t < 6e5) return Promise.resolve(c.v);
  if (HP.has(id)) return HP.get(id);
  const end = new Date(), start = new Date(end - 864e5);
  const p = h.callWS({type: "history/history_during_period", start_time: start.toISOString(), end_time: end.toISOString(), entity_ids: [id], minimal_response: true, no_attributes: true, significant_changes_only: true})
    .then(r => {
      const rows = (r && (r[id] || r[Object.keys(r)[0]])) || [], pts = [];
      for (const e of rows) { const t = e.lu != null ? e.lu * 1000 : Date.parse(e.last_changed || e.last_updated), v = parseFloat(e.s ?? e.state); if (!isNaN(v) && !isNaN(t)) pts.push([t, v]); }
      const N = 36, out = [];
      if (pts.length) { let j = 0; for (let i = 0; i < N; i++) { const T = +start + (i + 1) * 864e5 / N; while (j + 1 < pts.length && pts[j + 1][0] <= T) j++; out.push(pts[j][1]); } }
      if (HC.size >= 24) HC.delete(HC.keys().next().value);
      HC.set(id, {t: Date.now(), v: out});
      return out;
    }).catch(() => []).finally(() => HP.delete(id));
  HP.set(id, p);
  return p;
}
function spark(v, w = 120, hh = 32) {
  if (!v || v.length < 2) return "";
  const mn = Math.min(...v), mx = Math.max(...v), r = mx - mn || 1, p = 2, X = i => p + i * (w - 2 * p) / (v.length - 1), Y = x => hh - p - (x - mn) / r * (hh - 2 * p);
  let d = `M${X(0).toFixed(1)},${Y(v[0]).toFixed(1)}`;
  for (let i = 1; i < v.length; i++) { const x0 = X(i - 1), y0 = Y(v[i - 1]), x1 = X(i), y1 = Y(v[i]), cx = (x0 + x1) / 2; d += `C${cx.toFixed(1)},${y0.toFixed(1)} ${cx.toFixed(1)},${y1.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`; }
  return `<svg class="spk" viewBox="0 0 ${w} ${hh}" preserveAspectRatio="none" aria-hidden="true"><path d="${d}L${X(v.length - 1)},${hh}L${X(0)},${hh}Z" class="sa"/><path d="${d}" class="sl2"/></svg>`;
}

/* ---------- shared CSS ---------- */
const CSS = `
:host{display:block;--teo-r:24px;--c:var(--primary-color,#03a9f4);--ic:var(--state-inactive-color,var(--secondary-text-color,#9e9e9e));font-family:var(--ha-font-family-body,var(--paper-font-body1_-_font-family,Roboto,Noto,system-ui,sans-serif));-webkit-tap-highlight-color:transparent;color:var(--primary-text-color,#212121)}
*{box-sizing:border-box}
button{font:inherit;color:inherit}
.card{position:relative;overflow:hidden;border-radius:var(--teo-r);background:var(--ha-card-background,var(--card-background-color,#fff));border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color,rgba(0,0,0,.12)));box-shadow:var(--ha-card-box-shadow,none);transition:background .35s,border-color .35s,box-shadow .35s;isolation:isolate}
.card::before{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(135deg,color-mix(in srgb,var(--c) var(--tint,0%),transparent),transparent 72%);transition:background .35s}
.card.on{--tint:16%;--ic:var(--c)}
.glow{position:absolute;left:-30px;top:-34px;width:190px;height:170px;z-index:-1;pointer-events:none;background:radial-gradient(closest-side,color-mix(in srgb,var(--c) 55%,transparent),transparent);opacity:0;transition:opacity .5s}
.card.on .glow{opacity:var(--glow,.35)}
.hd{display:flex;align-items:center;gap:12px;padding:14px;min-height:72px}
.ico{position:relative;flex:none;width:44px;height:44px;border-radius:50%;display:grid;place-items:center;color:var(--ic);background:color-mix(in srgb,var(--ic) 17%,transparent);--mdc-icon-size:24px;cursor:pointer;transition:color .3s,background .3s,box-shadow .4s;overflow:hidden;outline:none}
.card.on .ico.gl{box-shadow:0 0 18px color-mix(in srgb,var(--c) 55%,transparent)}
.ico ha-icon{display:flex}
.ico img,.av{width:100%;height:100%;object-fit:cover;border-radius:50%}
.tx{min-width:0;flex:1;cursor:pointer;outline:none;border-radius:12px}
.nm{font-size:15px;font-weight:600;line-height:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:.01em}
.st{font-size:13px;line-height:18px;color:var(--secondary-text-color,#727272);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card.on .st{color:color-mix(in srgb,var(--primary-text-color,#212121) 72%,transparent)}
.ico:focus-visible,.tx:focus-visible,.btn:focus-visible,.chip:focus-visible,.sw:focus-visible,.aa:focus-visible{outline:2px solid var(--c);outline-offset:2px}
.sw{flex:none;position:relative;width:46px;height:28px;border-radius:14px;border:0;padding:0;cursor:pointer;background:color-mix(in srgb,var(--secondary-text-color,#727272) 30%,transparent);transition:background .25s}
.sw::after{content:"";position:absolute;left:3px;top:3px;width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.35);transition:transform .25s cubic-bezier(.3,1.3,.5,1)}
.sw[aria-checked=true]{background:var(--c)}.sw[aria-checked=true]::after{transform:translateX(18px)}
.val{font-size:22px;font-weight:600;white-space:nowrap;letter-spacing:-.01em}.val small{font-size:13px;font-weight:500;color:var(--secondary-text-color,#727272);margin-left:2px}
.ct{display:flex;flex-direction:column;gap:10px;padding:0 14px 14px}
.row{display:flex;gap:8px;flex-wrap:wrap}.row>*{flex:1 1 0;min-width:0}
.sl{position:relative;display:block;height:44px;border-radius:16px;background:color-mix(in srgb,var(--c) 18%,transparent);overflow:hidden;cursor:pointer;touch-action:pan-y;--p:0%}
.sl .fl{position:absolute;inset:0 auto 0 0;width:var(--p);background:linear-gradient(90deg,color-mix(in srgb,var(--c) 78%,#fff),var(--c));transition:width .18s}
.sl.drag .fl,.sl.drag .th{transition:none}
.sl .th{position:absolute;top:50%;left:clamp(10px,calc(var(--p) - 10px),calc(100% - 14px));width:4px;height:20px;margin-top:-10px;border-radius:2px;background:#fff;box-shadow:0 0 3px rgba(0,0,0,.45);pointer-events:none;transition:left .18s}
.sl.hue,.sl.kel{background:linear-gradient(90deg,#f44,#fa0,#ee0,#4d4,#0dd,#46f,#d4d,#f44)}.sl.kel{background:linear-gradient(90deg,#ffa43a,#ffd9a5,#fff,#cfe3ff,#8fb8ff)}
.sl.hue .fl,.sl.kel .fl{display:none}.sl.hue .th,.sl.kel .th{width:12px;height:12px;margin:-6px 0 0;border-radius:50%;border:3px solid #fff;background:transparent;box-shadow:0 0 4px rgba(0,0,0,.5)}
.sl input{position:absolute;inset:0;width:100%;height:100%;opacity:0;margin:0;cursor:pointer}
.sl:focus-within{outline:2px solid var(--c);outline-offset:2px}
.sl.thin{height:32px;border-radius:12px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:44px;padding:0 14px;border:0;border-radius:16px;cursor:pointer;background:color-mix(in srgb,var(--c) 14%,transparent);color:var(--primary-text-color,#212121);font-size:14px;font-weight:600;--mdc-icon-size:20px;transition:background .2s,transform .1s;white-space:nowrap}
.btn:hover{background:color-mix(in srgb,var(--c) 24%,transparent)}.btn:active{transform:scale(.96)}
.btn.on{background:var(--c);color:var(--teo-on,#fff)}.btn[disabled]{opacity:.4;pointer-events:none}
.btn.ic{flex:0 0 44px;padding:0}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 14px 0 10px;border-radius:18px;cursor:pointer;background:color-mix(in srgb,var(--c) 12%,var(--ha-card-background,var(--card-background-color,#fff)));border:1px solid var(--ha-card-border-color,var(--divider-color,rgba(0,0,0,.12)));font-size:13px;font-weight:600;--mdc-icon-size:18px;white-space:nowrap;transition:background .2s,transform .1s;color:var(--primary-text-color,#212121);outline:none}
.chip:active{transform:scale(.96)}.chip.on{background:var(--c);border-color:transparent;color:var(--teo-on,#fff)}
.chip ha-icon{display:flex;color:var(--cc,var(--c))}.chip.on ha-icon{color:inherit}
.chip.sm{height:32px;padding:0 12px;font-weight:500}
.step{display:flex;align-items:center;justify-content:center;gap:18px}
.step .btn{width:48px;height:48px;border-radius:50%;padding:0;--mdc-icon-size:24px}
.step .tv{min-width:96px;text-align:center;font-size:34px;font-weight:600;letter-spacing:-.02em;line-height:1}.step .tv small{font-size:16px;font-weight:500;color:var(--secondary-text-color)}
.sp{height:34px;margin:0 14px 14px}.spk{width:100%;height:100%;display:block;overflow:visible}.spk .sa{fill:color-mix(in srgb,var(--c) 18%,transparent)}.spk .sl2{fill:none;stroke:var(--c);stroke-width:2;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.pill{display:inline-flex;align-items:center;gap:4px;height:26px;padding:0 10px;border-radius:13px;background:color-mix(in srgb,var(--c) 14%,transparent);font-size:12px;font-weight:600;--mdc-icon-size:15px;white-space:nowrap}
.cam{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:color-mix(in srgb,var(--c) 10%,transparent)}
select.sel{width:100%;height:44px;border-radius:16px;border:0;padding:0 14px;background:color-mix(in srgb,var(--c) 14%,transparent);color:var(--primary-text-color,#212121);font:600 14px inherit;font-family:inherit;cursor:pointer}
.err{padding:16px;color:var(--error-color,#db4437);font-size:13px}
.l-compact .hd{min-height:56px;padding:8px 12px;gap:10px}.l-compact .ico{width:38px;height:38px;--mdc-icon-size:22px}.l-compact .nm{font-size:14px}
.l-big .hd{padding:18px 18px 8px;align-items:flex-start;flex-wrap:wrap}.l-big .ico{width:56px;height:56px;--mdc-icon-size:30px}.l-big .nm{font-size:17px}.l-big .st{font-size:14px}.l-big .val{font-size:40px;line-height:1.1;width:100%;margin-top:6px}
.l-big .ct{padding:6px 18px 18px;gap:12px}.l-big .sl{height:52px;border-radius:18px}.l-big .sp{height:56px;margin:0 18px 18px}
@keyframes spin{to{transform:rotate(360deg)}}@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.14)}}@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}@keyframes shake{0%,100%{transform:rotate(0)}25%{transform:rotate(-12deg)}75%{transform:rotate(12deg)}}@keyframes breathe{0%,100%{opacity:.75}50%{opacity:1}}
.an-spin ha-icon{animation:spin var(--dur,2s) linear infinite}.an-pulse ha-icon{animation:pulse 2.6s ease-in-out infinite}.an-bounce ha-icon{animation:bounce 1.1s ease-in-out infinite}.an-shake ha-icon{animation:shake .6s ease-in-out infinite}.an-breathe ha-icon{animation:breathe 2.4s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){.card *{animation:none!important;transition:none!important}}
`;

/* ---------- ui helpers ---------- */
const ico = (n, cls) => `<ha-icon${cls ? ` class="${cls}"` : ""} icon="${esc(n)}"></ha-icon>`;
const pctOf = (v, a, b) => b === a ? 0 : clamp((v - a) / (b - a) * 100, 0, 100);
const slider = o => `<label class="sl ${o.cls || ""}" style="--p:${pctOf(o.val, o.min, o.max).toFixed(1)}%"><input type="range" min="${o.min}" max="${o.max}" step="${o.step || 1}" value="${o.val}" aria-label="${esc(o.label)}" data-s="${o.s || ""}" data-f="${o.f || ""}"${o.e ? ` data-e="${esc(o.e)}"` : ""}${o.x ? ` data-x="${esc(JSON.stringify(o.x))}"` : ""}${o.z ? ` data-z="${o.z}"` : ""}${o.sat ? ` data-sat="${o.sat}"` : ""}><i class="fl"></i><i class="th"></i></label>`;
const btn = (o) => `<button class="btn${o.on ? " on" : ""}${o.ic ? " ic" : ""}" data-s="${o.s || ""}"${o.d ? ` data-d="${esc(JSON.stringify(o.d))}"` : ""}${o.e ? ` data-e="${esc(o.e)}"` : ""}${o.a ? ` data-a="${o.a}"` : ""}${o.v != null ? ` data-v="${esc(o.v)}"` : ""} aria-label="${esc(o.label)}"${o.on != null ? ` aria-pressed="${!!o.on}"` : ""}${o.dis ? " disabled" : ""} title="${esc(o.label)}">${o.i ? ico(o.i) : ""}${o.ic ? "" : esc(o.label)}</button>`;
const relTime = (h, iso) => { const s = (Date.now() - Date.parse(iso)) / 1000; try { const f = new Intl.RelativeTimeFormat(lang(h), {numeric: "auto"}); if (s < 60) return f.format(0, "second") ; if (s < 3600) return f.format(-Math.round(s / 60), "minute"); if (s < 86400) return f.format(-Math.round(s / 3600), "hour"); return f.format(-Math.round(s / 86400), "day"); } catch (e) { return ""; } };
const fmtDur = s => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60, p = n => String(n).padStart(2, "0"); return (h ? h + ":" : "") + p(m) + ":" + p(x); };
const imgUrl = (h, u) => !u ? "" : (/^(data:|https?:)/.test(u) ? u : (h && h.hassUrl ? h.hassUrl(u) : u));

/* ---------- base card ---------- */
class Base extends HTMLElement {
  constructor() {
    super();
    const r = this._r = this.attachShadow({mode: "open"});
    r.innerHTML = `<style>${CSS}${this.constructor.css || ""}</style><div id="m"></div>`;
    this._m = r.getElementById("m");
    this._cfg = null; this._h = null; this._html = ""; this._drag = false;
    r.addEventListener("click", e => this._onClick(e));
    r.addEventListener("input", e => this._onInput(e));
    r.addEventListener("change", e => this._onChange(e));
    r.addEventListener("pointerdown", e => this._pd(e));
    for (const t of ["pointerup", "pointercancel", "pointerleave"]) r.addEventListener(t, () => clearTimeout(this._hold));
    r.addEventListener("contextmenu", e => { if (e.target.closest && e.target.closest(".aa,[data-a=icon]")) e.preventDefault(); });
    r.addEventListener("keydown", e => {
      const t = e.target;
      if ((e.key === "Enter" || e.key === " ") && t.matches && t.matches('[role=button],[role=switch]') && t.tagName !== "BUTTON") { e.preventDefault(); t.click(); }
    });
  }
  setConfig(c) { if (!c || typeof c !== "object") throw new Error("Invalid configuration"); this._cfg = this._norm({...c}); this._html = ""; this._fresh(); }
  _norm(c) { return c; }
  _ids() { return arr(this._cfg.entity); }
  get hass() { return this._h; }
  set hass(h) { const o = this._h; this._h = h; if (this._cfg && (this._dyn || this._chg(o, h))) this._fresh(); }
  _chg(o, h) { if (!o || o.locale !== h.locale || o.language !== h.language) return true; return this._ids().some(i => o.states[i] !== h.states[i]); }
  _fresh() {
    if (!this._h) return;
    if (this._drag) { this._dirty = true; return; }
    let html;
    try { html = this._tpl(this._h, this._cfg); } catch (e) { console.error("[teo-cards]", e); html = `<div class="card"><div class="err">${esc(e.message)}</div></div>`; }
    if (html === this._html) return;
    this._html = html;
    const sel = 'button,input,select,[tabindex="0"]', ae = this._r.activeElement;
    const idx = ae ? [...this._m.querySelectorAll(sel)].indexOf(ae) : -1;
    this._m.innerHTML = html;
    if (idx >= 0) { const n = this._m.querySelectorAll(sel)[idx]; if (n) n.focus({preventScroll: true}); }
    this._post();
  }
  _post() {
    if (this._tick && !this._iv) this._iv = setInterval(() => this._tick && this._tick(), 1000);
    else if (!this._tick && this._iv) { clearInterval(this._iv); this._iv = 0; }
  }
  connectedCallback() { if (this._cfg && this._h) this._post(); }
  disconnectedCallback() { clearInterval(this._iv); this._iv = 0; clearTimeout(this._hold); clearTimeout(this._settle); clearTimeout(this._tt); }
  getCardSize() { return 2; }
  /* --- interaction --- */
  _acfg(t) { return {entity: this._cfg.entity, tap_action: this._cfg.tap_action, hold_action: this._cfg.hold_action, double_tap_action: this._cfg.double_tap_action, def: {tap: {action: "more-info"}, hold: {action: "none"}}}; }
  _doAct(t, kind) {
    const c = this._acfg(t); if (!c) return;
    const a = c[kind + "_action"] || (c.def && c.def[kind]) || {action: kind === "tap" ? "more-info" : "none"};
    runAction(this, this._h, a, c.entity);
  }
  _pd(e) {
    const t = e.target.closest && e.target.closest(".aa,[data-a=icon]"); if (!t) return;
    this._held = false; clearTimeout(this._hold);
    this._hold = setTimeout(() => { this._held = true; this._doAct(t, "hold"); }, 500);
  }
  _tap(t) {
    if (this._held) { this._held = false; return; }
    const c = this._acfg(t), d = c && c.double_tap_action;
    if (d && d.action && d.action !== "none") {
      if (this._dt && this._dt.t === t) { clearTimeout(this._dt.id); this._dt = null; this._doAct(t, "double_tap"); }
      else this._dt = {t, id: setTimeout(() => { this._dt = null; this._doAct(t, "tap"); }, 260)};
    } else this._doAct(t, "tap");
  }
  _onClick(e) {
    if (e.target.matches && e.target.matches("input,select,option")) return;
    const t = e.target.closest && e.target.closest("[data-s],[data-a],.aa"); if (!t) return;
    if (t.dataset.s) { this._svc(t); return; }
    if (t.dataset.a === "icon") { this._tap(t); return; }
    if (t.dataset.a) { this._act(t.dataset.a, t, e); return; }
    this._tap(t);
  }
  _act() {}
  _svc(t) {
    const [d, s] = t.dataset.s.split("."), data = t.dataset.d ? JSON.parse(t.dataset.d) : {};
    if (!("entity_id" in data) && t.dataset.n == null) data.entity_id = t.dataset.e || this._cfg.entity;
    haptic("light"); this._h.callService(d, s, data);
  }
  _onInput(e) {
    const i = e.target;
    if (i.type === "range") { this._drag = true; clearTimeout(this._settle); const s = i.closest(".sl"); s.classList.add("drag"); s.style.setProperty("--p", pctOf(+i.value, +i.min, +i.max) + "%"); if (this._live) this._live(i); }
  }
  _onChange(e) {
    const i = e.target;
    if (i.type === "range") { if (i.dataset.s) this._slide(i); else if (this._slideCustom) this._slideCustom(i); clearTimeout(this._settle); this._settle = setTimeout(() => { this._drag = false; if (this._dirty) { this._dirty = false; this._fresh(); } }, 900); }
    else if (i.tagName === "SELECT" && i.dataset.s) { const [d, s] = i.dataset.s.split("."); this._h.callService(d, s, {entity_id: i.dataset.e || this._cfg.entity, [i.dataset.f]: i.value}); }
  }
  _slide(i) {
    let [d, s] = i.dataset.s.split("."), v = +i.value;
    const data = {entity_id: i.dataset.e || this._cfg.entity};
    if (i.dataset.z && v === 0) { [d, s] = i.dataset.z.split("."); }
    else if (i.dataset.f === "hs_color") data.hs_color = [v, +i.dataset.sat || 100];
    else data[i.dataset.f] = v;
    if (i.dataset.x && !(i.dataset.z && v === 0)) Object.assign(data, JSON.parse(i.dataset.x));
    haptic("light"); this._h.callService(d, s, data);
  }
}
Base.prototype.shell = function (cls, style, inner, glow) { return `<div class="card ${cls}" style="${style}">${glow == null ? "" : '<div class="glow"></div>'}${inner}</div>`; };

/* ---------- visual editor factory (ha-form) ---------- */
const ACT = {selector: {ui_action: {}}};
function defineEditor(tag, schema, opts = {}) {
  class E extends HTMLElement {
    setConfig(c) { this._c = c; this._render(); }
    set hass(h) { this._h = h; if (this._f) this._f.hass = h; }
    _render() {
      if (!this._f) {
        const f = this._f = document.createElement("ha-form");
        f.computeLabel = s => tr(this._h, s.name);
        f.addEventListener("value-changed", e => { e.stopPropagation(); let v = e.detail.value; if (opts.from) v = opts.from(v, this._c); this._c = v; fire(this, "config-changed", {config: v}); });
        this.appendChild(f);
        if (opts.hint) { const p = document.createElement("p"); p.style.cssText = "font-size:12px;color:var(--secondary-text-color);margin:8px 4px 0"; p.textContent = tr(this._h, opts.hint); this.appendChild(p); }
      }
      this._f.hass = this._h; this._f.data = opts.to ? opts.to(this._c) : this._c; this._f.schema = schema(this._c);
    }
  }
  customElements.define(tag, E);
}
const reg = (type, name, description, cls) => { customElements.define(type, cls); (window.customCards = window.customCards || []).push({type, name, description, preview: true, documentationURL: "https://teodorteo.com"}); };
const Entities = {
  to: c => ({...c, entities: arr(c.entities).map(e => typeof e === "string" ? e : e.entity).filter(Boolean)}),
  from: (v, old) => { const prev = arr(old && old.entities); return {...v, entities: arr(v.entities).map(id => prev.find(p => p && typeof p === "object" && p.entity === id) || id)}; },
};
const sel = {
  layout: {name: "layout", selector: {select: {mode: "box", options: [{value: "tile", label: "Tile"}, {value: "compact", label: "Compact"}, {value: "big", label: "Big"}]}}},
  color: {name: "color", selector: {select: {custom_value: true, options: COLOR_NAMES.map(c => ({value: c, label: pretty(c.replace(/-/g, " "))}))}}},
};

/* ---------- teo-card : universal entity card ---------- */
const TOG = new Set(["light", "switch", "input_boolean", "fan", "humidifier", "automation", "siren", "group", "valve"]);
const RUN = {button: "button.press", input_button: "input_button.press", scene: "scene.turn_on", script: "script.turn_on", automation: "automation.trigger"};
const WX = {"clear-night": "night", cloudy: "cloudy", fog: "fog", hail: "hail", lightning: "lightning", "lightning-rainy": "lightning-rainy", partlycloudy: "partly-cloudy", pouring: "pouring", rainy: "rainy", snowy: "snowy", "snowy-rainy": "snowy-rainy", sunny: "sunny", windy: "windy", "windy-variant": "windy-variant", exceptional: "alert-circle-outline"};
const WXC = {sunny: "#ffb300", "clear-night": "#7986cb", rainy: "#42a5f5", pouring: "#1e88e5", snowy: "#80deea", lightning: "#fdd835", "lightning-rainy": "#7e57c2", fog: "#90a4ae", cloudy: "#90a4ae", partlycloudy: "#78909c", windy: "#4db6ac"};
const unitT = h => (h && h.config && h.config.unit_system && h.config.unit_system.temperature) || "°C";

function sensorColor(st) {
  const dc = st.attributes.device_class, v = num(st.state);
  if (v == null) return "var(--primary-color,#03a9f4)";
  if (dc === "temperature") { const c = st.attributes.unit_of_measurement === "°F" ? (v - 32) / 1.8 : v; return c <= 10 ? "#42a5f5" : c <= 18 ? "#26c6da" : c <= 24 ? "#66bb6a" : c <= 28 ? "#ffa726" : "#ef5350"; }
  if (dc === "battery") return v <= 15 ? "#ef5350" : v <= 40 ? "#ffa726" : "#66bb6a";
  if (dc === "humidity" || dc === "moisture") return "#29b6f6";
  if (["power", "energy", "current", "voltage", "apparent_power", "power_factor"].includes(dc)) return "#fbc02d";
  if (dc === "illuminance") return "#ffca28";
  if (dc === "carbon_dioxide") return v < 800 ? "#66bb6a" : v < 1200 ? "#ffa726" : "#ef5350";
  if (dc === "pm25" || dc === "aqi") return v < 25 ? "#66bb6a" : v < 50 ? "#ffa726" : "#ef5350";
  return "var(--primary-color,#03a9f4)";
}
const SDC = {temperature: "thermometer", humidity: "water-percent", battery: "battery", power: "flash", energy: "lightning-bolt", illuminance: "brightness-5", pressure: "gauge", carbon_dioxide: "molecule-co2", voltage: "sine-wave", current: "current-ac", signal_strength: "wifi", duration: "timer-outline", speed: "speedometer", water: "water", gas: "fire", monetary: "cash"};
const BDC = {motion: ["motion-sensor", "motion-sensor-off"], door: ["door-open", "door-closed"], window: ["window-open", "window-closed"], garage_door: ["garage-open", "garage"], opening: ["square-outline", "square"], smoke: ["smoke-detector-variant", "smoke-detector-variant"], moisture: ["water", "water-off"], occupancy: ["home", "home-outline"], presence: ["home", "home-outline"], battery: ["battery-alert", "battery"], connectivity: ["lan-connect", "lan-disconnect"], plug: ["power-plug", "power-plug-off"], problem: ["alert-circle", "check-circle"], lock: ["lock-open", "lock"], vibration: ["vibrate", "crop-portrait"], gas: ["alert-circle", "check-circle"], light: ["brightness-7", "brightness-5"], sound: ["music-note", "music-note-off"]};
const BDCOL = {motion: "#ef5350", occupancy: "#ef5350", presence: "#66bb6a", door: "#ffa726", window: "#ffa726", garage_door: "#ffa726", opening: "#ffa726", smoke: "#e53935", gas: "#e53935", moisture: "#29b6f6", problem: "#e53935", safety: "#e53935", battery: "#ef5350", connectivity: "#66bb6a", plug: "#66bb6a", lock: "#ffa726", vibration: "#ab47bc"};

function icoFor(st) {
  const d = dom(st.entity_id), s = st.state, a = st.attributes, on = !OFFS.includes(s), dc = a.device_class;
  if (a.icon) return a.icon;
  const m = n => "mdi:" + n;
  switch (d) {
    case "light": return m(on ? "lightbulb" : "lightbulb-outline");
    case "switch": return m(dc === "outlet" ? "power-socket-eu" : on ? "toggle-switch" : "toggle-switch-off");
    case "input_boolean": return m(on ? "toggle-switch" : "toggle-switch-off");
    case "fan": return m(on ? "fan" : "fan-off");
    case "humidifier": return m("air-humidifier");
    case "cover": { const o = s !== "closed"; return m({garage: o ? "garage-open" : "garage", door: o ? "door-open" : "door-closed", gate: o ? "gate-open" : "gate", window: o ? "window-open" : "window-closed"}[dc] || (["blind", "curtain", "shade", "shutter"].includes(dc) ? (o ? "blinds-open" : "blinds") : (o ? "window-shutter-open" : "window-shutter"))); }
    case "climate": return m("thermostat");
    case "lock": return m({locked: "lock", unlocked: "lock-open-variant", jammed: "lock-alert", open: "lock-open-variant"}[s] || "lock-clock");
    case "vacuum": return m("robot-vacuum");
    case "alarm_control_panel": return m({disarmed: "shield-off", armed_home: "shield-home", armed_away: "shield-lock", armed_night: "shield-moon", triggered: "bell-ring", pending: "shield-alert", arming: "shield-sync"}[s] || "shield");
    case "sensor": return m(SDC[dc] || "eye");
    case "binary_sensor": { const p = BDC[dc]; return m(p ? p[on ? 0 : 1] : on ? "checkbox-marked-circle" : "radiobox-blank"); }
    case "weather": return m("weather-" + (WX[s] || "cloudy"));
    case "person": return m("account");
    case "device_tracker": return m("cellphone");
    case "button": case "input_button": return m("gesture-tap-button");
    case "scene": return m("palette");
    case "script": return m("script-text-play");
    case "automation": return m("robot");
    case "media_player": return m(dc === "tv" ? "television" : dc === "receiver" ? "audio-video" : "speaker");
    case "update": return m(s === "on" ? "package-up" : "package-check");
    case "camera": return m("video");
    case "timer": return m("timer-outline");
    case "select": case "input_select": return m("format-list-bulleted");
    case "number": case "input_number": return m("tune");
    case "siren": return m("bullhorn");
    default: return m("eye");
  }
}

class TeoCard extends Base {
  static css = `.hd .tx{align-self:center}.sub2{display:flex;gap:6px;flex-wrap:wrap}`;
  _norm(c) { if (!c.entity) throw new Error("teo-card: 'entity' is required"); c.layout = ["tile", "compact", "big"].includes(c.layout) ? c.layout : "tile"; return c; }
  getCardSize() { return this._cfg && this._cfg.layout === "compact" ? 1 : 3; }
  getGridOptions() { const l = this._cfg && this._cfg.layout; return l === "compact" ? {columns: 6, min_columns: 3, rows: 1, min_rows: 1} : {columns: 12, min_columns: 4, rows: "auto"}; }
  static getStubConfig(h, ents) { const p = (ents || Object.keys((h && h.states) || {})).find(e => /^(light|switch|climate|cover|sensor|fan)\./.test(e)); return {type: "custom:teo-card", entity: p || "light.living_room", layout: "tile"}; }
  static getConfigElement() { return document.createElement("teo-card-editor"); }
  _acfg(t) {
    const c = this._cfg, ic = t.dataset && t.dataset.a === "icon", d = dom(c.entity);
    if (ic) return {entity: c.entity, tap_action: c.icon_tap_action, hold_action: c.hold_action || {action: "more-info"}, def: {tap: TOG.has(d) ? {action: "toggle"} : RUN[d] ? {action: "perform-action", perform_action: RUN[d]} : {action: "more-info"}, hold: {action: "more-info"}}};
    return {entity: c.entity, tap_action: c.tap_action, hold_action: c.hold_action, double_tap_action: c.double_tap_action, def: {tap: {action: "more-info"}, hold: {action: "none"}}};
  }
  _doAct(t, kind) {
    const c = this._acfg(t), a = c[kind + "_action"] || c.def[kind], d = dom(c.entity);
    if (a && a.action === "perform-action" && a.perform_action === RUN[d] && !a.data && !a.target) { this._h.callService(...RUN[d].split("."), {entity_id: c.entity}); haptic("medium"); return; }
    runAction(this, this._h, a, c.entity);
  }
  _act(a, t) {
    if (a === "ex") { this._ex = !this._ex; this._html = ""; this._fresh(); }
    else if (a === "step") this._step(t.dataset.k, +t.dataset.v);
    else if (a === "alarm") { const st = this._h.states[this._cfg.entity]; this._h.callService("alarm_control_panel", t.dataset.m, {entity_id: this._cfg.entity, ...(this._code ? {code: this._code} : {})}); haptic("medium"); }
  }
  _onInput(e) { const i = e.target; if (i.dataset && i.dataset.a === "code") { this._code = i.value; return; } super._onInput(e); }
  _step(k, v) {
    const st = this._h.states[this._cfg.entity], a = st.attributes, t = this._tg = this._tg || {};
    const cur = t[k] ?? a[k], mn = a.min_temp ?? 7, mx = a.max_temp ?? 35;
    t[k] = clamp(Math.round((cur + v) * 100) / 100, mn, mx);
    this._html = ""; this._fresh();
    clearTimeout(this._tt);
    this._tt = setTimeout(() => {
      const d = {entity_id: this._cfg.entity}; for (const x in this._tg) d[x] = this._tg[x];
      this._tg = null; this._h.callService("climate", "set_temperature", d);
    }, 700);
    haptic("light");
  }
  _tpl(h, c) {
    const st = h.states[c.entity], lay = c.layout;
    if (!st) return this.shell("", "", `<div class="err">${esc(c.entity)}: ${esc(tr(h, "unavailable"))}</div>`);
    const d = dom(c.entity), a = st.attributes, s = st.state, name = c.name || a.friendly_name || c.entity;
    const o = this._info(h, st, d, lay, c);
    let col = color(c.color) || o.color || "var(--primary-color,#03a9f4)";
    if (c.color === "state" && o.color) col = o.color;
    const icon = c.icon || icoFor(st);
    let sub = o.sub ?? sTxt(h, st);
    if (c.secondary_info) { const x = c.secondary_info === "last-changed" ? relTime(h, st.last_changed) : a[c.secondary_info]; if (x != null && x !== "") sub = lay === "compact" ? `${x}` : `${sub} · ${x}`; }
    const an = c.animate === false || !o.an ? "" : "an-" + o.an;
    const icoInner = o.pic ? `<img src="${esc(imgUrl(h, o.pic))}" alt="">` : ico(icon);
    const sw = o.sw ? `<button class="sw" role="switch" aria-checked="${o.on}" aria-label="${esc(name)}" data-s="${o.on ? (d === "cover" ? "" : "homeassistant.turn_off") : "homeassistant.turn_on"}"></button>` : "";
    const val = o.val != null ? `<div class="val">${o.val}</div>` : "";
    let ctl = lay === "compact" ? (o.cctl || "") : (o.ctl || "");
    let spk = "";
    if (o.graph && lay !== "compact") { spk = this._sp && this._sp.id === c.entity ? this._sp.v : null; if (spk == null) { const e = c.entity; history(h, e).then(v => { this._sp = {id: e, v}; this._html = ""; this._fresh(); }); } spk = spk && spk.length > 1 ? `<div class="sp" aria-hidden="true">${spark(spk)}</div>` : ""; }
    const top = o.top || "";
    const hdVal = lay === "big" ? val : "";
    const aria = `${name}, ${sub}`;
    const hd = `<div class="hd"><div class="ico ${o.gl ? "gl " : ""}${an}" data-a="icon" role="button" tabindex="0" aria-label="${esc(aria)}">${icoInner}</div><div class="tx aa" role="button" tabindex="0" aria-label="${esc(name)}"><div class="nm">${esc(name)}</div><div class="st">${esc(sub)}</div></div>${lay === "big" ? "" : val}${sw}${hdVal}</div>`;
    const dur = o.dur ? `--dur:${o.dur}s;` : "";
    return this.shell(`l-${lay}${o.on ? " on" : ""}`, `--c:${col};${o.glow != null ? `--glow:${o.glow};` : ""}${dur}`, `${top}${hd}${ctl ? `<div class="ct">${ctl}</div>` : ""}${spk}`, 1);
  }
  _info(h, st, d, lay, c) {
    const a = st.attributes, s = st.state, un = s === "unavailable", o = {on: !OFFS.includes(s)}, big = lay === "big", ex = this._ex || big, t = k => tr(h, k), f = a.supported_features || 0;
    const slid = (x) => slider({e: c.entity, ...x});
    if (un) { o.on = false; o.sub = t("unavailable"); return o; }
    switch (d) {
      case "light": {
        const on = s === "on", modes = arr(a.supported_color_modes), bri = a.brightness != null ? Math.round(a.brightness / 2.55) : on ? 100 : 0;
        const hasB = modes.some(m => m !== "onoff"), hasCT = modes.includes("color_temp"), hasC = modes.some(m => ["hs", "xy", "rgb", "rgbw", "rgbww"].includes(m));
        o.on = on; o.sw = true; o.gl = true; o.an = on ? "breathe" : ""; o.glow = on ? (0.2 + bri / 100 * 0.45).toFixed(2) : 0;
        o.color = a.rgb_color && on ? `rgb(${a.rgb_color.join(",")})` : "var(--state-light-active-color,#ffb300)";
        o.sub = on ? (hasB ? `${t("on")} · ${bri}%` : t("on")) : t("off");
        if (hasB) {
          const sl = slid({min: 1, max: 100, val: Math.max(1, bri), label: "Brightness", s: "light.turn_on", f: "brightness_pct", z: "light.turn_off"});
          o.ctl = (hasCT || hasC) && !big ? `<div style="display:flex;gap:8px"><div style="flex:1;min-width:0;display:flex;flex-direction:column">${sl}</div>${btn({ic: 1, a: "ex", i: ex ? "mdi:chevron-up" : "mdi:palette", label: t("colors")})}</div>` : sl;
          if (on && ex) {
            const k = a.color_temp_kelvin;
            if (hasCT) o.ctl += slid({min: a.min_color_temp_kelvin || 2000, max: a.max_color_temp_kelvin || 6500, step: 50, val: k || 3000, label: "Colour temperature", s: "light.turn_on", f: "color_temp_kelvin", cls: "kel" + (big ? "" : " thin")});
            if (hasC) o.ctl += slid({min: 0, max: 360, val: a.hs_color ? a.hs_color[0] : 0, label: "Hue", s: "light.turn_on", f: "hs_color", sat: a.hs_color && a.hs_color[1] > 25 ? a.hs_color[1] : 100, cls: "hue" + (big ? "" : " thin")});
          }
        }
        return o;
      }
      case "switch": case "input_boolean": case "siren": case "valve": case "group": o.sw = true; o.sub = sTxt(h, st); o.color = d === "switch" ? "var(--state-switch-active-color,#ffa726)" : ""; return o;
      case "automation": o.sw = true; o.ctl = btn({s: "automation.trigger", i: "mdi:play", label: t("run")}); return o;
      case "fan": {
        const p = a.percentage, on = s === "on"; o.sw = true; o.color = "#26c6da"; o.an = on ? "spin" : ""; o.dur = on ? (3 - (p ?? 50) / 100 * 2.6).toFixed(2) : 0;
        o.sub = on ? (p != null ? `${t("on")} · ${p}%` : t("on")) : t("off");
        if (f & 1) o.ctl = slid({min: 1, max: 100, step: a.percentage_step || 1, val: p || 1, label: "Speed", s: "fan.set_percentage", f: "percentage", z: "fan.turn_off"});
        if ((f & 8) && arr(a.preset_modes).length && (big || lay === "tile")) o.ctl = (o.ctl || "") + `<div class="chips">${a.preset_modes.map(m => `<button class="chip sm${a.preset_mode === m ? " on" : ""}" data-s="fan.set_preset_mode" data-d='${esc(JSON.stringify({entity_id: c.entity, preset_mode: m}))}'>${esc(pretty(m))}</button>`).join("")}</div>`;
        return o;
      }
      case "humidifier": {
        o.sw = true; o.color = "#4fc3f7"; o.an = o.on ? "pulse" : "";
        o.sub = o.on ? `${t("on")} · ${a.humidity ?? "-"}%${a.current_humidity != null ? ` (${a.current_humidity}%)` : ""}` : t("off");
        if (a.min_humidity != null || a.humidity != null) o.ctl = slid({min: a.min_humidity ?? 0, max: a.max_humidity ?? 100, val: a.humidity ?? 50, label: "Humidity", s: "humidifier.set_humidity", f: "humidity"});
        return o;
      }
      case "cover": {
        const pos = a.current_position, closedish = s === "closed"; o.on = !closedish; o.color = "#8e7cf0"; o.an = s === "opening" || s === "closing" ? "bounce" : "";
        o.sub = t(s) + (pos != null && s !== "closed" ? ` · ${pos}%` : "");
        const b = [];
        if (f & 1) b.push(btn({s: "cover.open_cover", i: "mdi:arrow-up", label: t("open")}));
        if (f & 8) b.push(btn({s: "cover.stop_cover", i: "mdi:stop", label: t("stop")}));
        if (f & 2) b.push(btn({s: "cover.close_cover", i: "mdi:arrow-down", label: t("close")}));
        o.ctl = ((f & 4) && pos != null ? slid({min: 0, max: 100, val: pos, label: "Position", s: "cover.set_cover_position", f: "position"}) : "") + (b.length ? `<div class="row">${b.join("")}</div>` : "");
        return o;
      }
      case "climate": {
        const act = a.hvac_action, unit = unitT(h), cur = a.current_temperature, tg = this._tg || {};
        o.color = act === "heating" || (!act && s === "heat") ? "#ff7043" : act === "cooling" || (!act && s === "cool") ? "#42a5f5" : act === "drying" ? "#ffa726" : s === "heat_cool" || s === "auto" ? "#26a69a" : s === "fan_only" ? "#26c6da" : "#66bb6a";
        o.an = act === "heating" || act === "cooling" ? "pulse" : "";
        o.sub = `${t(act && act !== "off" ? act : s)}${cur != null ? ` · ${cur}${unit}` : ""}`;
        o.val = cur != null && !big ? `${cur}<small>${esc(unit)}</small>` : (big && cur != null ? `${cur}<small>${esc(unit)}</small>` : null);
        const stp = a.target_temp_step || (unit === "°F" ? 1 : 0.5);
        const stepper = (k, v, lbl) => `<div class="step" ${lbl ? `role="group" aria-label="${esc(lbl)}"` : ""}>${btn({ic: 1, a: "step", v: -stp, i: "mdi:minus", label: "−"}).replace("<button", `<button data-k="${k}"`)}<div class="tv" aria-live="polite">${(tg[k] ?? v)}<small>${esc(unit)}</small></div>${btn({ic: 1, a: "step", v: stp, i: "mdi:plus", label: "+"}).replace("<button", `<button data-k="${k}"`)}</div>`;
        let ctl = "";
        if (s !== "off") {
          if (a.temperature != null) ctl += stepper("temperature", a.temperature, t("target"));
          else if (a.target_temp_low != null && a.target_temp_high != null) ctl += stepper("target_temp_low", a.target_temp_low, "min") + stepper("target_temp_high", a.target_temp_high, "max");
        }
        o.cctl = "";
        const modes = arr(a.hvac_modes);
        if (modes.length) ctl += `<div class="chips">${modes.map(m => `<button class="chip sm${m === s ? " on" : ""}" aria-pressed="${m === s}" data-s="climate.set_hvac_mode" data-d='${esc(JSON.stringify({entity_id: c.entity, hvac_mode: m}))}'>${esc(t(m))}</button>`).join("")}</div>`;
        o.ctl = ctl; return o;
      }
      case "lock": {
        o.on = s === "locked"; o.color = s === "locked" ? "#43a047" : s === "jammed" ? "#e53935" : "#ffa000"; o.an = s === "locking" || s === "unlocking" ? "pulse" : "";
        const lk = s === "locked";
        o.cctl = ""; o.ctl = btn({s: lk ? "lock.unlock" : "lock.lock", i: lk ? "mdi:lock-open" : "mdi:lock", label: lk ? t("unlock") : t("lock"), on: !lk});
        return o;
      }
      case "vacuum": {
        const cl = s === "cleaning" || s === "returning"; o.on = cl; o.color = "#26a69a"; o.an = s === "cleaning" ? "bounce" : "";
        o.sub = t(s) + (a.battery_level != null ? ` · ${a.battery_level}%` : "");
        const b = [];
        if (cl) b.push(btn({s: f & 4 ? "vacuum.pause" : "vacuum.stop", i: "mdi:pause", label: t("pause")})); else b.push(btn({s: "vacuum.start", i: "mdi:play", label: t("start"), on: 1}));
        if (f & 16) b.push(btn({s: "vacuum.return_to_base", i: "mdi:home", label: t("dock")}));
        if (f & 512) b.push(btn({s: "vacuum.locate", i: "mdi:map-marker", label: t("locate")}));
        o.ctl = `<div class="row">${b.join("")}</div>`; return o;
      }
      case "alarm_control_panel": {
        const dis = s === "disarmed"; o.on = !dis; o.color = dis ? "#43a047" : s === "pending" || s === "arming" ? "#ffa726" : "#e53935"; o.an = s === "triggered" ? "shake" : "";
        const b = [];
        if (dis) { if (f & 1) b.push(["alarm_arm_home", "mdi:shield-home", "arm_home"]); if (f & 2) b.push(["alarm_arm_away", "mdi:shield-lock", "arm_away"]); if (f & 4) b.push(["alarm_arm_night", "mdi:shield-moon", "arm_night"]); }
        else b.push(["alarm_disarm", "mdi:shield-off", "disarm"]);
        const code = a.code_format ? `<input class="sel" style="padding:0 14px;border:0" type="password" inputmode="numeric" autocomplete="off" placeholder="${esc(t("code"))}" aria-label="${esc(t("code"))}" data-a="code" value="${esc(this._code || "")}">` : "";
        o.ctl = code + `<div class="row">${b.map(x => btn({a: "alarm", i: x[1], label: t(x[2])}).replace("<button", `<button data-m="${x[0]}"`)).join("")}</div>`; return o;
      }
      case "sensor": {
        const v = num(s), dc = a.device_class; o.on = v != null; o.color = sensorColor(st); o.sub = pretty(dc || a.friendly_name ? (dc ? dc.replace(/_/g, " ") : "") : "") || "";
        const u = a.unit_of_measurement; o.val = v != null || s ? `${esc(s)}${u ? `<small>${esc(u)}</small>` : ""}` : null; o.pic = null;
        o.sub = dc ? pretty(dc) : st.attributes.state_class ? pretty(st.attributes.state_class) : t("current");
        o.graph = v != null && (c.graph || (big && c.graph !== false)); return o;
      }
      case "binary_sensor": { const dc = a.device_class; o.color = BDCOL[dc] || ""; o.sub = BIN(h, dc, s); o.an = o.on && (dc === "smoke" || dc === "gas") ? "shake" : ""; return o; }
      case "weather": {
        o.on = true; o.color = WXC[s] || "#78909c"; o.sub = pretty(s.replace(/-/g, " ")); o.val = a.temperature != null ? `${a.temperature}<small>${esc(a.temperature_unit || unitT(h))}</small>` : null;
        const p = []; if (a.humidity != null) p.push(["water-percent", a.humidity + "%"]); if (a.wind_speed != null) p.push(["weather-windy", `${a.wind_speed} ${a.wind_speed_unit || ""}`]); if (a.pressure != null) p.push(["gauge", `${a.pressure} ${a.pressure_unit || ""}`]);
        o.ctl = p.length ? `<div class="chips">${p.map(x => `<span class="pill">${ico("mdi:" + x[0])}${esc(x[1])}</span>`).join("")}</div>` : ""; o.an = s === "sunny" ? "pulse" : ""; return o;
      }
      case "person": case "device_tracker": { o.on = s === "home"; o.color = "#43a047"; o.pic = a.entity_picture; o.sub = s === "home" || s === "not_home" ? t(s) : s; return o; }
      case "button": case "input_button": case "scene": case "script": {
        o.on = d === "script" && s === "on"; o.color = d === "scene" ? "#ab47bc" : "";
        const lbl = d === "button" || d === "input_button" ? t("press") : t("run");
        o.sub = d === "scene" || d === "button" || d === "input_button" ? "" : sTxt(h, st); if (!o.sub) o.sub = lbl;
        o.ctl = btn({s: RUN[d], i: d === "button" || d === "input_button" ? "mdi:gesture-tap" : "mdi:play", label: lbl, on: 1}); return o;
      }
      case "media_player": {
        const pl = s === "playing", idle = ["off", "standby"].includes(s), ttl = a.media_title;
        o.on = !idle && s !== "unavailable"; o.color = "#9575cd"; o.pic = a.entity_picture; o.an = pl ? "bounce" : "";
        o.sub = ttl ? `${ttl}${a.media_artist ? " · " + a.media_artist : ""}` : sTxt(h, st);
        const b = [];
        if (idle) b.push(btn({s: "media_player.turn_on", i: "mdi:power", label: t("on")}));
        else { if (f & 16) b.push(btn({s: "media_player.media_previous_track", i: "mdi:skip-previous", label: "Previous", ic: 1})); b.push(btn({s: "media_player.media_play_pause", i: pl ? "mdi:pause" : "mdi:play", label: pl ? t("pause") : t("start"), on: 1, ic: 1})); if (f & 32) b.push(btn({s: "media_player.media_next_track", i: "mdi:skip-next", label: "Next", ic: 1})); }
        let ctl = `<div class="row" style="justify-content:center">${b.join("")}</div>`;
        if (big && !idle && (f & 4) && a.volume_level != null) ctl += slid({min: 0, max: 100, val: Math.round(a.volume_level * 100), label: "Volume", s: "media_player.volume_set", f: "volume_level", cls: "thin"}).replace('data-f="volume_level"', 'data-f="volume_level" data-div="100"');
        o.ctl = ctl; return o;
      }
      case "update": {
        const on = s === "on"; o.color = "#ffa726"; o.an = on ? "bounce" : ""; o.sub = on ? `${a.installed_version || ""} → ${a.latest_version || ""}` : t("up_to_date");
        if (a.in_progress) { o.sub = (typeof a.in_progress === "number" ? a.in_progress + "% " : "") + "…"; }
        if (on && (f & 1) && !a.in_progress) o.ctl = btn({s: "update.install", i: "mdi:download", label: t("install"), on: 1}); return o;
      }
      case "camera": {
        o.color = ""; const p = a.entity_picture;
        o.top = p ? `<div class="aa" role="button" tabindex="0" aria-label="${esc(a.friendly_name || c.entity)}"><img class="cam" src="${esc(imgUrl(h, p))}" alt="" onerror="this.style.display='none'"></div>` : "";
        o.sub = sTxt(h, st); this._tick = null; return o;
      }
      case "timer": {
        const act = s === "active", pa = s === "paused"; o.on = act || pa; o.color = "#ffa000"; o.an = act ? "spin" : ""; o.dur = 6;
        const rem = () => act ? (Date.parse(a.finishes_at) - Date.now()) / 1000 : this._tsec(a.remaining);
        o.val = o.on ? `<span data-tm>${fmtDur(rem())}</span>` : null; o.sub = t(s);
        if (act) { this._tick = () => { const n = this._m.querySelector("[data-tm]"), r = rem(); if (n) n.textContent = fmtDur(r); if (r < -2) this._tick = null; }; this._post(); } else { this._tick = null; this._post(); }
        o.ctl = `<div class="row">${act ? btn({s: "timer.pause", i: "mdi:pause", label: t("pause")}) : btn({s: "timer.start", i: "mdi:play", label: t("start"), on: 1})}${o.on ? btn({s: "timer.cancel", i: "mdi:close", label: t("cancel")}) : ""}</div>`; return o;
      }
      case "select": case "input_select": {
        o.on = true; o.sub = s; o.ctl = `<select class="sel" aria-label="${esc(c.name || a.friendly_name || c.entity)}" data-s="${d}.select_option" data-f="option">${arr(a.options).map(x => `<option${x === s ? " selected" : ""}>${esc(x)}</option>`).join("")}</select>`; return o;
      }
      case "number": case "input_number": {
        const v = num(s); o.on = true; o.val = `${esc(s)}${a.unit_of_measurement ? `<small>${esc(a.unit_of_measurement)}</small>` : ""}`; o.sub = pretty(d.replace("_", " "));
        if (v != null) o.ctl = slid({min: a.min ?? 0, max: a.max ?? 100, step: a.step || 1, val: v, label: c.name || a.friendly_name || "Value", s: d + ".set_value", f: "value"});
        return o;
      }
      default: o.on = !OFFS.includes(s); o.sub = sTxt(h, st); return o;
    }
  }
  _tsec(r) { const p = String(r || "0").split(":").map(Number); return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : (p[0] || 0); }
  _slide(i) {
    if (i.dataset.div) { const v = +i.value / +i.dataset.div; haptic("light"); const [d, s] = i.dataset.s.split("."); this._h.callService(d, s, {entity_id: this._cfg.entity, [i.dataset.f]: v}); return; }
    super._slide(i);
  }
}
const cardSchema = c => [
  {name: "entity", required: true, selector: {entity: {}}},
  {name: "name", selector: {text: {}}},
  {name: "icon", selector: {icon: {}}},
  {type: "grid", name: "", schema: [{...sel.layout}, {...sel.color}]},
  {type: "grid", name: "", schema: [{name: "graph", selector: {boolean: {}}}, {name: "animate", selector: {boolean: {}}}]},
  {name: "secondary_info", selector: {text: {}}},
  {name: "tap_action", ...ACT}, {name: "icon_tap_action", ...ACT}, {name: "hold_action", ...ACT}, {name: "double_tap_action", ...ACT},
];
defineEditor("teo-card-editor", cardSchema);
reg("teo-card", "Teo Card", "Universal, beautiful entity card for any domain (lights, climate, covers, sensors, media, ...).", TeoCard);

/* ---------- shared: small colour logic for chips / room / stats ---------- */
function quickColor(st) {
  const d = dom(st.entity_id), s = st.state, a = st.attributes;
  if (d === "sensor") return sensorColor(st);
  if (d === "binary_sensor") return BDCOL[a.device_class] || "";
  if (d === "light") return a.rgb_color && s === "on" ? `rgb(${a.rgb_color.join(",")})` : "#ffb300";
  if (d === "person" || d === "device_tracker") return "#43a047";
  if (d === "weather") return WXC[s] || "#78909c";
  if (d === "alarm_control_panel") return s === "disarmed" ? "#43a047" : s === "triggered" ? "#e53935" : "#ef6c00";
  if (d === "climate") return s === "off" ? "" : a.hvac_action === "cooling" || s === "cool" ? "#42a5f5" : a.hvac_action === "heating" || s === "heat" ? "#ff7043" : "#66bb6a";
  if (d === "cover") return "#8e7cf0";
  if (d === "fan") return "#26c6da";
  if (d === "lock") return s === "locked" ? "#43a047" : "#ffa000";
  if (d === "media_player") return "#9575cd";
  return "";
}
const isOn = st => !!st && !OFFS.includes(st.state) && !["closed", "locked", "disarmed", "not_home", "docked", "idle", "standby"].includes(st.state);
const listDom = (h, d) => Object.keys(h.states || {}).filter(k => k.startsWith(d + "."));

/* ---------- teo-chips ---------- */
class TeoChips extends Base {
  static css = `.chips{padding:2px 0}.chip{box-shadow:var(--ha-card-box-shadow,none)}.chip small{color:var(--secondary-text-color);font-weight:500}`;
  _norm(c) {
    const e = arr(c.entities); if (!e.length) throw new Error("teo-chips: 'entities' is required");
    this._items = e.map(x => typeof x === "string" ? {entity: x} : {...x});
    for (const i of this._items) i.type = i.type || (i.entity ? ({weather: "weather", alarm_control_panel: "alarm", person: "person"}[dom(i.entity)] || "entity") : "label");
    this._dyn = this._items.some(i => ["battery", "people", "lights"].includes(i.type));
    c.entity = null; return c;
  }
  _ids() { return this._items.map(i => i.entity).filter(Boolean); }
  getCardSize() { return 1; }
  getGridOptions() { return {columns: 12, min_columns: 3, rows: 1}; }
  static getStubConfig(h) { return {type: "custom:teo-chips", entities: [{type: "people"}, {type: "battery"}, {type: "lights"}]}; }
  static getConfigElement() { return document.createElement("teo-chips-editor"); }
  _acfg(t) {
    const i = this._items[+t.dataset.i], d = {tap: {action: "more-info"}, hold: {action: "none"}};
    if (i.type === "lights" || i.type === "battery" || i.type === "people") d.tap = i.type === "lights" && this._lon && this._lon.length ? {action: "perform-action", perform_action: "light.turn_off", target: {entity_id: this._lon}} : {action: "none"};
    return {entity: i.entity, tap_action: i.tap_action, hold_action: i.hold_action, double_tap_action: i.double_tap_action, def: d};
  }
  _tpl(h, c) {
    const out = [];
    this._items.forEach((i, n) => {
      const st = i.entity ? h.states[i.entity] : null, T = k => tr(h, k);
      let ic, text = "", col = color(i.color), on = false, label = i.name || "";
      if (i.type === "label") { ic = i.icon; text = i.text || ""; }
      else if (i.type === "people") {
        const p = listDom(h, "person"), home = p.filter(e => h.states[e].state === "home").length;
        ic = i.icon || "mdi:account-group"; text = `${home}/${p.length}`; label = i.name || T("people_home"); col = col || "#43a047"; on = home > 0; i.show_name = i.show_name ?? true;
      } else if (i.type === "battery") {
        const th = i.threshold ?? 20;
        const low = Object.keys(h.states).filter(k => { const s = h.states[k], dc = s.attributes.device_class; return dc === "battery" && ((k.startsWith("sensor.") && num(s.state) != null && num(s.state) <= th) || (k.startsWith("binary_sensor.") && s.state === "on")); });
        if (!low.length && !i.show_zero) return;
        ic = i.icon || "mdi:battery-alert"; text = String(low.length); label = i.name || T("battery_low"); col = col || (low.length ? "#ef5350" : "#66bb6a"); on = low.length > 0; i.show_name = i.show_name ?? true;
      } else if (i.type === "lights") {
        const on_ = listDom(h, "light").filter(k => h.states[k].state === "on"); this._lon = on_;
        ic = i.icon || "mdi:lightbulb-group"; text = String(on_.length); label = i.name || T("lights_on"); col = col || "#ffb300"; on = on_.length > 0; i.show_name = i.show_name ?? true;
        if (!on_.length && i.hide_if_zero) return;
      } else {
        if (!st) return;
        const d = dom(st.entity_id);
        ic = i.icon || icoFor(st); col = col || quickColor(st); on = isOn(st) || d === "sensor";
        if (d === "weather") text = st.attributes.temperature != null ? `${st.attributes.temperature}${st.attributes.temperature_unit || unitT(h)}` : sTxt(h, st);
        else if (i.show_state !== false) text = sTxt(h, st);
        label = i.show_name ? (i.name || st.attributes.friendly_name || i.entity) : "";
      }
      const name = i.show_name ? (label || "") : "";
      const lab = [name, text].filter(Boolean).join(" ");
      out.push(`<div class="chip aa" role="button" tabindex="0" data-i="${n}" aria-label="${esc(lab || ic)}" style="--c:${col || "var(--primary-color,#03a9f4)"};--cc:${on && col ? col : "var(--secondary-text-color)"}">${ic ? ico(ic) : ""}${text ? `<span>${esc(text)}</span>` : ""}${name && i.type !== "entity" ? `<small>${esc(name)}</small>` : name ? `<small>${esc(name)}</small>` : ""}</div>`);
    });
    const al = {start: "flex-start", center: "center", end: "flex-end"}[c.alignment] || "flex-start";
    return `<div class="chips" role="list" style="justify-content:${al}">${out.join("")}</div>`;
  }
}
defineEditor("teo-chips-editor", c => [{name: "entities", selector: {entity: {multiple: true}}}, {name: "alignment", selector: {select: {mode: "dropdown", options: ["start", "center", "end"]}}}], {...Entities, hint: "chips_hint"});
reg("teo-chips", "Teo Chips", "A row of small chips: entity states, weather, alarm, people at home, low batteries, lights on.", TeoChips);

/* ---------- teo-title ---------- */
class TeoTitle extends Base {
  static css = `:host{--c:var(--primary-color,#03a9f4)}.t{padding:6px 4px}.t.c{text-align:center}.t.r{text-align:right}
h2{margin:0;font-size:30px;line-height:1.15;font-weight:700;letter-spacing:-.02em;background:linear-gradient(100deg,var(--primary-text-color,#212121) 55%,var(--c));-webkit-background-clip:text;background-clip:text;color:transparent}
.t.m h2{font-size:24px}.t.s h2{font-size:19px}
p{margin:4px 0 0;font-size:15px;color:var(--secondary-text-color,#727272)}p.dt{font-size:13px;text-transform:capitalize;letter-spacing:.02em}`;
  _norm(c) { this._dyn = true; return c; }
  _ids() { return []; }
  getCardSize() { return 1; }
  getGridOptions() { return {columns: 12, min_columns: 3, rows: "auto"}; }
  static getStubConfig() { return {type: "custom:teo-title", greeting: true, subtitle: "Welcome home", show_date: true}; }
  static getConfigElement() { return document.createElement("teo-title-editor"); }
  _tpl(h, c) {
    const hr = new Date().getHours(), k = hr >= 22 || hr < 5 ? "night" : hr < 12 ? "morning" : hr < 18 ? "afternoon" : "evening";
    const nm = c.name || ((h.user && h.user.name) || "").split(" ")[0];
    const g = tr(h, k);
    let title = c.title != null ? c.title : (c.greeting ? "{greeting}, {name}" : "");
    title = String(title).replace(/\{greeting\}/g, g).replace(/\{name\}/g, nm).replace(/,\s*$/, "").replace(/^,\s*/, "");
    const dt = c.show_date ? new Intl.DateTimeFormat(lang(h), {weekday: "long", day: "numeric", month: "long"}).format(new Date()) : "";
    return `<div class="t ${{center: "c", right: "r"}[c.align] || ""} ${{medium: "m", small: "s"}[c.size] || ""}">${dt ? `<p class="dt">${esc(dt)}</p>` : ""}${title ? `<h2>${esc(title)}</h2>` : ""}${c.subtitle ? `<p>${esc(c.subtitle)}</p>` : ""}</div>`;
  }
}
defineEditor("teo-title-editor", c => [{name: "title", selector: {text: {}}}, {name: "subtitle", selector: {text: {}}}, {name: "greeting", selector: {boolean: {}}}, {name: "name", selector: {text: {}}}, {name: "show_date", selector: {boolean: {}}},
  {name: "align", selector: {select: {mode: "dropdown", options: ["left", "center", "right"]}}}, {name: "size", selector: {select: {mode: "dropdown", options: ["large", "medium", "small"]}}}]);
reg("teo-title", "Teo Title", "Big title and subtitle with a greeting by time of day and the user's name.", TeoTitle);

/* ---------- teo-room ---------- */
const ROOMDOM = ["light", "switch", "fan", "cover", "climate", "media_player", "lock", "vacuum", "input_boolean", "scene", "script", "camera"];
const MORE = new Set(["climate", "media_player", "lock", "vacuum", "camera", "sensor", "binary_sensor"]);
class TeoRoom extends Base {
  static css = `.hd{padding:16px 16px 10px;align-items:flex-start}.ico{width:48px;height:48px}.bd{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.rb{display:grid;grid-template-columns:repeat(auto-fill,minmax(64px,1fr));gap:8px;padding:2px 14px 14px}
.rbt{display:flex;flex-direction:column;align-items:center;gap:4px;padding:10px 4px 8px;border-radius:18px;cursor:pointer;background:color-mix(in srgb,var(--secondary-text-color,#727272) 10%,transparent);--mdc-icon-size:24px;min-width:0;outline:none;transition:background .25s,transform .1s;color:var(--secondary-text-color,#727272)}
.rbt:active{transform:scale(.95)}.rbt.on{background:color-mix(in srgb,var(--bc) 22%,transparent);color:var(--bc)}.rbt ha-icon{display:flex}
.rbt span{font-size:11px;line-height:14px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--primary-text-color,#212121);font-weight:500}
.lt{flex:none;align-self:flex-start}.lt.btn{min-height:40px;border-radius:20px}`;
  _norm(c) { if (!c.area && !arr(c.entities).length && !arr(c.buttons).length) throw new Error("teo-room: set 'area' or 'entities'"); this._dyn = false; return c; }
  _ids() { return this._rv ? this._rv.all : []; }
  _chg(o, h) { const r = this._res(h); return !o || o.entities !== h.entities || o.areas !== h.areas || super._chg(o, h); }
  getCardSize() { return 3; }
  getGridOptions() { return {columns: 12, min_columns: 6, rows: "auto"}; }
  static getStubConfig(h) { const a = h && h.areas ? Object.keys(h.areas)[0] : ""; return a ? {type: "custom:teo-room", area: a} : {type: "custom:teo-room", name: "Living room", icon: "mdi:sofa", entities: []}; }
  static getConfigElement() { return document.createElement("teo-room-editor"); }
  _res(h) {
    const c = this._cfg, key = [h.entities, h.devices, h.areas, c];
    if (this._rk && this._rk.every((x, i) => x === key[i]) && this._rv) return this._rv;
    let ids = arr(c.entities).map(x => typeof x === "string" ? x : x.entity);
    if (c.area && h.entities) ids = ids.concat(Object.values(h.entities).filter(e => !e.hidden && !e.entity_category && (e.area_id === c.area || (!e.area_id && e.device_id && h.devices && h.devices[e.device_id] && h.devices[e.device_id].area_id === c.area))).map(e => e.entity_id));
    ids = [...new Set(ids)].filter(i => h.states[i]);
    const dc = (i, x) => i.startsWith("sensor.") && h.states[i].attributes.device_class === x;
    const temp = c.temperature_entity || ids.find(i => dc(i, "temperature")), hum = c.humidity_entity || ids.find(i => dc(i, "humidity"));
    const lights = ids.filter(i => i.startsWith("light.")), btns = arr(c.buttons).length ? arr(c.buttons) : ids.filter(i => ROOMDOM.includes(dom(i))).sort((x, y) => ROOMDOM.indexOf(dom(x)) - ROOMDOM.indexOf(dom(y))).slice(0, c.max_buttons || 8);
    this._rk = key;
    return (this._rv = {temp, hum, lights, btns, all: [...new Set([temp, hum, ...lights, ...btns].filter(Boolean))]});
  }
  _acfg(t) {
    if (t.dataset.i != null) {
      const id = this._rv.btns[+t.dataset.i], d = dom(id);
      return {entity: id, def: {tap: MORE.has(d) ? {action: "more-info"} : d === "cover" ? {action: "perform-action", perform_action: "cover.toggle", target: {entity_id: id}} : d === "scene" || d === "script" ? {action: "perform-action", perform_action: d + ".turn_on", target: {entity_id: id}} : {action: "toggle"}, hold: {action: "more-info"}}};
    }
    return {entity: this._cfg.entity, tap_action: this._cfg.tap_action, hold_action: this._cfg.hold_action, double_tap_action: this._cfg.double_tap_action, def: {tap: this._cfg.navigation_path ? {action: "navigate", navigation_path: this._cfg.navigation_path} : {action: "none"}, hold: {action: "none"}}};
  }
  _tpl(h, c) {
    const r = this._res(h), T = k => tr(h, k), ar = c.area && h.areas && h.areas[c.area];
    const name = c.name || (ar && ar.name) || pretty(c.area || "Room"), icon = c.icon || (ar && ar.icon) || "mdi:sofa";
    const lon = r.lights.filter(i => h.states[i].state === "on"), anyOn = lon.length > 0;
    const col = color(c.color) || (anyOn ? "#ffb300" : "var(--primary-color,#03a9f4)");
    const bd = [];
    if (r.temp) { const s = h.states[r.temp]; bd.push(`<span class="pill">${ico("mdi:thermometer")}${esc(sTxt(h, s))}</span>`); }
    if (r.hum) { const s = h.states[r.hum]; bd.push(`<span class="pill">${ico("mdi:water-percent")}${esc(sTxt(h, s))}</span>`); }
    const lt = r.lights.length ? btn({s: anyOn ? "light.turn_off" : "light.turn_on", d: {entity_id: anyOn ? lon : r.lights}, i: "mdi:lightbulb", label: anyOn ? `${lon.length}/${r.lights.length} ${T("on").toLowerCase()}` : T("all_on"), on: anyOn}).replace('class="btn', 'class="btn lt').replace('aria-pressed', `title="${esc(anyOn ? T("all_off") : T("all_on"))}" aria-pressed`) : "";
    const rb = r.btns.map((id, n) => {
      const s = h.states[id], on = isOn(s) && !(dom(id) === "cover" && s.state === "closed"), bc = quickColor(s) || "var(--primary-color,#03a9f4)";
      const nm = s.attributes.friendly_name || id;
      return `<div class="rbt aa${on ? " on" : ""}" role="button" tabindex="0" data-i="${n}" style="--bc:${bc}" aria-label="${esc(nm + ", " + sTxt(h, s))}" aria-pressed="${on}">${ico(s.attributes.icon || icoFor(s))}<span>${esc(nm.replace(new RegExp("^" + name + "\\s*", "i"), "") || nm)}</span></div>`;
    }).join("");
    return this.shell(anyOn ? "on" : "", `--c:${col};--glow:.4`, `<div class="hd"><div class="ico gl aa" role="button" tabindex="0" aria-label="${esc(name)}">${ico(icon)}</div><div class="tx"><div class="nm" style="font-size:17px">${esc(name)}</div>${bd.length ? `<div class="bd">${bd.join("")}</div>` : ""}</div>${lt}</div>${rb ? `<div class="rb">${rb}</div>` : ""}`, 1);
  }
}
defineEditor("teo-room-editor", c => [{name: "area", selector: {area: {}}}, {name: "name", selector: {text: {}}}, {name: "icon", selector: {icon: {}}}, {name: "color", ...sel.color},
  {name: "temperature_entity", selector: {entity: {domain: "sensor", device_class: "temperature"}}}, {name: "humidity_entity", selector: {entity: {domain: "sensor", device_class: "humidity"}}},
  {name: "entities", selector: {entity: {multiple: true}}}, {name: "buttons", selector: {entity: {multiple: true}}}, {name: "tap_action", ...ACT}]);
reg("teo-room", "Teo Room", "Area-aware room card: temperature/humidity, lights-on count with one-tap all off, and main entity buttons.", TeoRoom);

/* ---------- teo-stats ---------- */
class TeoStats extends Base {
  static css = `.g{display:grid;gap:12px;grid-template-columns:repeat(var(--n,auto-fit),minmax(var(--w,130px),1fr))}
.tl{display:flex;flex-direction:column;padding:14px 14px 0;min-height:112px;cursor:pointer;outline:none}.tl.nograph{padding-bottom:14px}
.top{display:flex;align-items:center;gap:8px;min-width:0}.top .ico{width:30px;height:30px;--mdc-icon-size:18px;cursor:inherit}.top .nm{font-size:12px;font-weight:500;color:var(--secondary-text-color,#727272)}
.v{font-size:30px;line-height:36px;font-weight:700;letter-spacing:-.02em;margin-top:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v small{font-size:13px;font-weight:500;color:var(--secondary-text-color,#727272);margin-left:3px;letter-spacing:0}
.tl .sp{margin:auto -14px 0;height:36px;opacity:.95}.tl .spk .sa{fill:color-mix(in srgb,var(--c) 22%,transparent)}.tl .spk{overflow:hidden}
.ttl{font-size:15px;font-weight:600;padding:0 4px 8px}`;
  _norm(c) { const e = arr(c.entities); if (!e.length) throw new Error("teo-stats: 'entities' is required"); this._items = e.map(x => typeof x === "string" ? {entity: x} : {...x}); this._sps = {}; c.entity = null; return c; }
  _ids() { return this._items.map(i => i.entity); }
  getCardSize() { return 2; }
  getGridOptions() { return {columns: 12, min_columns: 6, rows: 2, min_rows: 2}; }
  static getStubConfig(h) { const s = Object.keys((h && h.states) || {}).filter(k => k.startsWith("sensor.")).slice(0, 3); return {type: "custom:teo-stats", entities: s.length ? s : ["sensor.power", "sensor.temperature"]}; }
  static getConfigElement() { return document.createElement("teo-stats-editor"); }
  _acfg(t) { const i = this._items[+t.dataset.i]; return {entity: i.entity, tap_action: i.tap_action, hold_action: i.hold_action, double_tap_action: i.double_tap_action, def: {tap: {action: "more-info"}, hold: {action: "none"}}}; }
  _tpl(h, c) {
    const tiles = this._items.map((i, n) => {
      const st = h.states[i.entity]; if (!st) return "";
      const v = num(st.state), col = color(i.color) || sensorColor(st), u = i.unit ?? st.attributes.unit_of_measurement ?? "", graph = i.graph !== false && c.graph !== false && v != null;
      const txt = v != null && i.decimals != null ? v.toFixed(i.decimals) : st.state;
      let sp = "";
      if (graph) { const s = this._sps[i.entity]; if (s) sp = `<div class="sp" aria-hidden="true">${spark(s, 120, 36)}</div>`; else { const e = i.entity; this._sps[e] = null; history(h, e).then(x => { this._sps[e] = x; this._html = ""; this._fresh(); }); } }
      const nm = i.name || st.attributes.friendly_name || i.entity;
      return this.shell("on", `--c:${col};--glow:.18`, `<div class="tl aa${graph ? "" : " nograph"}" role="button" tabindex="0" data-i="${n}" aria-label="${esc(`${nm}: ${txt} ${u}`)}"><div class="top"><div class="ico">${ico(i.icon || icoFor(st))}</div><div class="nm">${esc(nm)}</div></div><div class="v">${esc(txt)}<small>${esc(u)}</small></div>${sp}</div>`, 1);
    }).join("");
    return `${c.title ? `<div class="ttl">${esc(c.title)}</div>` : ""}<div class="g" style="${c.columns ? `--n:${+c.columns};` : ""}">${tiles}</div>`;
  }
}
defineEditor("teo-stats-editor", c => [{name: "title", selector: {text: {}}}, {name: "entities", selector: {entity: {multiple: true}}}, {name: "columns", selector: {number: {min: 1, max: 6, mode: "box"}}}, {name: "graph", selector: {boolean: {}}}], {...Entities, hint: "chips_hint"});
reg("teo-stats", "Teo Stats", "A row of big number tiles (energy, power, temperature) with a tiny 24h sparkline.", TeoStats);

/* ---------- teo-media : player + lazy media library browser ---------- */
const MCI = {directory: "folder", music: "music-note", track: "music-note", album: "album", artist: "account-music", playlist: "playlist-music", video: "movie", movie: "movie", tv_show: "television-play", image: "image", channel: "radio", podcast: "podcast", app: "apps", genre: "folder-music"};
class TeoMedia extends Base {
  static css = `.card{--c:#9575cd;min-height:150px}
.bg{position:absolute;inset:-30px;z-index:-2;background-size:cover;background-position:center;filter:blur(34px) saturate(1.4);transform:scale(1.1);opacity:0;transition:opacity .6s}
.card.art .bg{opacity:1}.card.art::after{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(180deg,rgba(0,0,0,.38),rgba(0,0,0,.62))}
.card.art{color:#fff;--primary-text-color:#fff;--secondary-text-color:rgba(255,255,255,.76);border-color:transparent}
.card.art .btn{background:rgba(255,255,255,.16);color:#fff}.card.art .btn.on{background:#fff;color:#222}.card.art .chip{background:rgba(255,255,255,.14);border-color:rgba(255,255,255,.18);color:#fff}.card.art .chip.on{background:#fff;color:#222}.card.art select.sel{background:rgba(255,255,255,.16);color:#fff}.card.art select.sel option{color:#222}
.card.art .sl{background:rgba(255,255,255,.22)}.card.art .sl .fl{background:#fff}
.mp{padding:16px;display:flex;flex-direction:column;gap:14px}
.top{display:flex;gap:14px;align-items:center}
.cv{flex:none;width:92px;height:92px;border-radius:20px;overflow:hidden;display:grid;place-items:center;background:linear-gradient(135deg,color-mix(in srgb,var(--c) 70%,#fff),var(--c));color:#fff;box-shadow:0 8px 22px rgba(0,0,0,.28);--mdc-icon-size:42px}
.cv img{width:100%;height:100%;object-fit:cover}.cv ha-icon{display:flex}
.top .tx{cursor:default}.top .nm{font-size:19px;line-height:25px;white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}.top .st{font-size:14px}.top .st.s2{font-size:12px;opacity:.85}
.pr{display:flex;align-items:center;gap:10px;font-size:12px;font-variant-numeric:tabular-nums;color:var(--secondary-text-color)}.pr .sl{flex:1;height:22px;border-radius:11px}.pr .sl.ro{pointer-events:none}.pr .sl .th{display:none}.pr .sl.rw .th{display:block;width:12px;height:12px;border-radius:50%;margin-top:-6px}.pr span{min-width:38px}.pr span:last-child{text-align:right}
.ctl{display:flex;align-items:center;justify-content:center;gap:14px}
.ctl .btn{--mdc-icon-size:26px}.ctl .btn.ic{flex:0 0 48px;width:48px;height:48px;border-radius:50%}.ctl .pp{flex:0 0 62px;width:62px;height:62px;border-radius:50%;--mdc-icon-size:32px}
.vol{display:flex;align-items:center;gap:10px}.vol .sl{flex:1;height:34px;border-radius:12px}
.act{display:flex;gap:8px;align-items:center}.act select{flex:1;min-width:0}
.spk2{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.spk2 b{font-size:12px;font-weight:600;color:var(--secondary-text-color);margin-right:2px}
.lib{display:flex;flex-direction:column;max-height:var(--teo-lib-h,520px)}
.lh{display:flex;align-items:center;gap:8px;padding:12px 12px 8px}.lh .btn{min-height:40px}
.bc{flex:1;min-width:0;display:flex;align-items:center;gap:2px;overflow-x:auto;scrollbar-width:none;white-space:nowrap;font-size:13px;font-weight:600}
.bc button{background:none;border:0;padding:6px 8px;border-radius:10px;cursor:pointer;color:var(--secondary-text-color);font-weight:600;font-size:13px}.bc button:last-child{color:var(--primary-text-color)}.bc button:hover{background:color-mix(in srgb,var(--c) 14%,transparent)}.bc i{opacity:.5;font-style:normal}
.fi{margin:0 12px 8px;height:40px;border-radius:14px;border:0;padding:0 14px;background:color-mix(in srgb,var(--c) 12%,transparent);color:var(--primary-text-color);font:inherit;font-size:14px;outline:none}.fi::-webkit-search-cancel-button{filter:grayscale(1) contrast(2)}.fi:focus{box-shadow:0 0 0 2px var(--c)}
.gr{display:grid;grid-template-columns:repeat(auto-fill,minmax(98px,1fr));gap:12px;padding:4px 12px 14px;overflow-y:auto;overscroll-behavior:contain}
.it{position:relative;display:flex;flex-direction:column;gap:6px;cursor:pointer;border-radius:16px;outline:none;min-width:0;padding:0}.it[hidden]{display:none}
.it .im{position:relative;aspect-ratio:1;border-radius:16px;overflow:hidden;display:grid;place-items:center;background:color-mix(in srgb,var(--c) 16%,transparent);color:var(--c);--mdc-icon-size:36px;transition:transform .15s}
.it:hover .im{transform:scale(1.03)}.it:focus-visible .im{outline:2px solid var(--c);outline-offset:2px}
.it .im img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.it .im ha-icon{display:flex}
.it .tt{font-size:12px;line-height:16px;font-weight:500;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.it .pl{position:absolute;right:6px;bottom:6px;width:32px;height:32px;border-radius:50%;border:0;padding:0;display:grid;place-items:center;background:var(--c);color:#fff;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.35);--mdc-icon-size:20px}
.msg{padding:32px 16px;text-align:center;color:var(--secondary-text-color);font-size:14px}.msg .btn{margin-top:12px}`;
  _norm(c) {
    if (!c.entity) throw new Error("teo-media: 'entity' is required");
    c.speakers = arr(c.speakers); this._br = null; return c;
  }
  _ids() { return [this._cfg.entity, ...this._cfg.speakers]; }
  getCardSize() { return 4; }
  getGridOptions() { return {columns: 12, min_columns: 6, rows: "auto"}; }
  static getStubConfig(h, ents) { const p = (ents || Object.keys((h && h.states) || {})).find(e => e.startsWith("media_player.")); return {type: "custom:teo-media", entity: p || "media_player.living_room", start_path: "media-source://media_source"}; }
  static getConfigElement() { return document.createElement("teo-media-editor"); }
  _acfg() { return {entity: this._cfg.entity, tap_action: this._cfg.tap_action, hold_action: this._cfg.hold_action, double_tap_action: this._cfg.double_tap_action, def: {tap: {action: "more-info"}, hold: {action: "none"}}}; }
  disconnectedCallback() { super.disconnectedCallback(); this._tick = null; }
  /* --- browser (nothing is fetched until the user opens the Library) --- */
  _root() { const p = this._cfg.start_path; return p && typeof p === "object" ? {id: p.media_content_id, type: p.media_content_type, title: p.title || tr(this._h, "library")} : {id: p || "media-source://media_source", type: undefined, title: tr(this._h, "library")}; }
  async _load(stack) {
    const br = this._br = {stack, node: null, loading: true, error: "", q: ""}, it = stack[stack.length - 1], h = this._h;
    this._html = ""; this._fresh();
    try {
      const msg = {type: "media_player/browse_media", entity_id: this._cfg.entity, media_content_id: it.id}; if (it.type) msg.media_content_type = it.type;
      const r = await h.callWS(msg);
      if (this._br !== br) return;
      br.node = r; br.loading = false;
    } catch (e) { if (this._br !== br) return; br.loading = false; br.error = (e && (e.message || e.code)) || tr(h, "failed"); }
    this._html = ""; this._fresh();
  }
  _act(a, t) {
    const br = this._br, h = this._h, c = this._cfg;
    if (a === "lib") this._load([this._root()]);
    else if (a === "close") { this._br = null; this._html = ""; this._fresh(); }
    else if (a === "up") { if (br.stack.length > 1) this._load(br.stack.slice(0, -1)); else this._act("close"); }
    else if (a === "crumb") this._load(br.stack.slice(0, +t.dataset.v + 1));
    else if (a === "retry") this._load(br.stack);
    else if (a === "open") { const ch = br.node.children[+t.dataset.v]; this._load([...br.stack, {id: ch.media_content_id, type: ch.media_content_type, title: ch.title}]); }
    else if (a === "play") {
      const ch = t.dataset.v != null ? br.node.children[+t.dataset.v] : br.node;
      h.callService("media_player", "play_media", {entity_id: c.entity, media_content_id: ch.media_content_id, media_content_type: ch.media_content_type}); haptic("medium");
      this._br = null; this._html = ""; this._fresh();
    } else if (a === "spk") {
      const id = t.dataset.v, gm = arr((h.states[c.entity] || {attributes: {}}).attributes.group_members);
      if (gm.includes(id)) h.callService("media_player", "unjoin", {entity_id: id}); else h.callService("media_player", "join", {entity_id: c.entity, group_members: [id]});
      haptic("light");
    } else if (a === "mute") { const st = h.states[c.entity]; h.callService("media_player", "volume_mute", {entity_id: c.entity, is_volume_muted: !st.attributes.is_volume_muted}); }
  }
  _onInput(e) {
    const i = e.target;
    if (i.dataset && i.dataset.a === "flt") { const q = i.value.toLowerCase(); this._br.q = q; this._html = this._html.replace(/(data-a="flt"[^>]*value=")[^"]*/, `$1${esc(i.value)}`); this._m.querySelectorAll(".it").forEach(n => { n.hidden = !!q && !n.dataset.t.includes(q); }); return; }
    super._onInput(e);
  }
  _slide(i) {
    if (i.dataset.div) { const v = +i.value / +i.dataset.div; haptic("light"); const [d, s] = i.dataset.s.split("."); this._h.callService(d, s, {entity_id: this._cfg.entity, [i.dataset.f]: v}); return; }
    super._slide(i);
  }
  _libHtml(h, c) {
    const br = this._br, T = k => tr(h, k), n = br.node;
    const crumbs = br.stack.map((s, i) => `<button data-a="crumb" data-v="${i}">${esc(i === 0 ? T("library") : s.title)}</button>`).join("<i>›</i>");
    let body;
    if (br.loading) body = `<div class="msg">${esc(T("loading"))}</div>`;
    else if (br.error) body = `<div class="msg">${esc(T("failed"))}<br><small>${esc(br.error)}</small><br>${btn({a: "retry", label: "Retry"})}</div>`;
    else {
      const ch = arr(n.children);
      body = ch.length ? `<input class="fi" type="search" data-a="flt" placeholder="${esc(T("search"))}" aria-label="${esc(T("search"))}" value="${esc(br.q)}"><div class="gr">${ch.map((x, i) => {
        const th = x.thumbnail ? `<img src="${esc(imgUrl(h, x.thumbnail))}" alt="" loading="lazy" onerror="this.remove()">` : "";
        const ic = MCI[x.media_class] || (x.can_expand ? "folder" : "music-note");
        const open = x.can_expand;
        return `<div class="it" role="button" tabindex="0" data-a="${open ? "open" : "play"}" data-v="${i}" data-t="${esc(String(x.title || "").toLowerCase())}" aria-label="${esc(x.title)}"${br.q && !String(x.title || "").toLowerCase().includes(br.q) ? " hidden" : ""}><div class="im">${ico("mdi:" + ic)}${th}${open && x.can_play ? `<button class="pl" data-a="play" data-v="${i}" aria-label="Play ${esc(x.title)}">${ico("mdi:play")}</button>` : ""}</div><div class="tt">${esc(x.title)}</div></div>`;
      }).join("")}</div>` : `<div class="msg">${esc(T("empty"))}</div>`;
    }
    return `<div class="lib"><div class="lh">${btn({ic: 1, a: "up", i: "mdi:arrow-left", label: T("back")})}<div class="bc" aria-label="Breadcrumb">${crumbs}</div>${n && n.can_play && !br.loading && !br.error ? btn({ic: 1, a: "play", i: "mdi:play", label: "Play all", on: 1}) : ""}${btn({ic: 1, a: "close", i: "mdi:close", label: "Close"})}</div>${body}</div>`;
  }
  _tpl(h, c) {
    const st = h.states[c.entity], T = k => tr(h, k);
    if (!st) return this.shell("", "", `<div class="err">${esc(c.entity)}: ${esc(T("unavailable"))}</div>`);
    const a = st.attributes, s = st.state, f = a.supported_features || 0, pl = s === "playing", idle = ["off", "standby", "unavailable"].includes(s);
    const pic = a.entity_picture ? imgUrl(h, a.entity_picture) : "", name = c.name || a.friendly_name || c.entity;
    const col = color(c.color);
    if (this._br) { this._tick = null; this._post(); return this.shell(`${pic ? "art" : ""}`, col ? `--c:${col}` : "", `<div class="bg"${pic ? ` style="background-image:url('${esc(pic)}')"` : ""}></div>` + this._libHtml(h, c), 1).replace('<div class="glow"></div>', ""); }
    const dur = num(a.media_duration), pos = () => (num(a.media_position) || 0) + (pl && a.media_position_updated_at ? (Date.now() - Date.parse(a.media_position_updated_at)) / 1000 : 0);
    const title = a.media_title || (idle ? T("nothing") : sTxt(h, st)), sub = [a.media_artist || a.media_series_title, a.media_album_name].filter(Boolean).join(" · ");
    const canSeek = !!(f & 2);
    const prog = dur && !idle ? `<div class="pr"><span data-tc>${fmtDur(pos())}</span><label class="sl thin ${canSeek ? "rw" : "ro"}" style="--p:${pctOf(pos(), 0, dur).toFixed(1)}%"><input type="range" min="0" max="${dur}" step="1" value="${Math.round(Math.min(pos(), dur))}" aria-label="Position" ${canSeek ? 'data-s="media_player.media_seek" data-f="seek_position"' : "disabled"}><i class="fl"></i><i class="th"></i></label><span>${fmtDur(dur)}</span></div>` : "";
    const b = [];
    if (idle) { if (f & 128) b.push(btn({s: "media_player.turn_on", i: "mdi:power", label: T("on"), on: 1})); }
    else {
      if (f & 16) b.push(btn({s: "media_player.media_previous_track", i: "mdi:skip-previous", label: "Previous", ic: 1}));
      b.push(btn({s: "media_player.media_play_pause", i: pl ? "mdi:pause" : "mdi:play", label: pl ? T("pause") : T("start"), on: 1, ic: 1}).replace('class="btn', 'class="btn pp'));
      if (f & 32) b.push(btn({s: "media_player.media_next_track", i: "mdi:skip-next", label: "Next", ic: 1}));
    }
    const vol = !idle && (f & 4) && a.volume_level != null ? `<div class="vol">${btn({ic: 1, a: "mute", i: a.is_volume_muted ? "mdi:volume-off" : "mdi:volume-high", label: "Mute"})}${slider({min: 0, max: 100, val: Math.round(a.volume_level * 100), label: "Volume", s: "media_player.volume_set", f: "volume_level", cls: "thin"}).replace('data-f="volume_level"', 'data-f="volume_level" data-div="100"')}</div>` : "";
    const srcs = arr(a.source_list), source = !idle && srcs.length ? `<select class="sel" aria-label="${esc(T("source"))}" data-s="media_player.select_source" data-f="source">${srcs.map(x => `<option${x === a.source ? " selected" : ""}>${esc(x)}</option>`).join("")}</select>` : "";
    const lib = (c.library === true || (c.library !== false && (f & 131072))) && s !== "unavailable" ? btn({a: "lib", i: "mdi:folder-music", label: T("library")}) : "";
    const gm = arr(a.group_members), spk = c.speakers.length ? `<div class="spk2" role="group" aria-label="${esc(T("speakers"))}"><b>${esc(T("speakers"))}</b>${c.speakers.map(id => { const x = h.states[id]; if (!x) return ""; return `<button class="chip sm${gm.includes(id) ? " on" : ""}" data-a="spk" data-v="${esc(id)}" aria-pressed="${gm.includes(id)}">${ico("mdi:speaker")}${esc(x.attributes.friendly_name || id)}</button>`; }).join("")}</div>` : "";
    if (pl && dur) this._tick = () => { if (this._drag || !this._m) return; const p = pos(), n = this._m.querySelector("[data-tc]"), sl = this._m.querySelector(".pr .sl"); if (n) n.textContent = fmtDur(p); if (sl) { sl.style.setProperty("--p", pctOf(p, 0, dur) + "%"); const i = sl.querySelector("input"); if (i) i.value = Math.round(Math.min(p, dur)); } }; else this._tick = null;
    this._post();
    const cover = pic ? `<img src="${esc(pic)}" alt="" onerror="this.remove()">` : ico("mdi:music");
    return this.shell(`${pic && !idle ? "art " : ""}${pl ? "on " : ""}`, col ? `--c:${col}` : "", `<div class="bg"${pic ? ` style="background-image:url('${esc(pic)}')"` : ""}></div><div class="mp"><div class="top"><div class="cv" aria-hidden="true">${cover}</div><div class="tx aa" role="button" tabindex="0" aria-label="${esc(name + ": " + title)}"><div class="nm">${esc(title)}</div>${sub ? `<div class="st">${esc(sub)}</div>` : ""}<div class="st s2">${esc(name)}${a.source ? " · " + esc(a.source) : ""}</div></div></div>${prog}<div class="ctl">${b.join("")}</div>${vol}<div class="act">${source}${lib}</div>${spk}</div>`, 1).replace('<div class="glow"></div>', "");
  }
}
defineEditor("teo-media-editor", c => [{name: "entity", required: true, selector: {entity: {domain: "media_player"}}}, {name: "name", selector: {text: {}}}, {name: "speakers", selector: {entity: {domain: "media_player", multiple: true}}},
  {name: "start_path", selector: {text: {}}}, {name: "color", ...sel.color}, {name: "tap_action", ...ACT}, {name: "hold_action", ...ACT}]);
reg("teo-media", "Teo Media", "Media player with cover-art backdrop, volume, sources, speaker groups and a media library browser (incl. media-source folders).", TeoMedia);

console.info(`%c HACardsTeo %c v${VERSION} `, "background:#7c4dff;color:#fff;border-radius:4px 0 0 4px;padding:2px 4px", "background:#333;color:#fff;border-radius:0 4px 4px 0;padding:2px 4px");
})();
