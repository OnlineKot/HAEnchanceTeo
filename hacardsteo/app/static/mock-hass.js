/* HACardsTeo gallery - fake Home Assistant (`hass` object) so the cards run standalone. By TeodorTeo.com */
(() => {
const MOCK = window.MOCK = {calls: [], cards: new Set()};
/* ha-icon stand-in (real Home Assistant provides its own) */
const EXTRA = {
  "arrow-left": "M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z",
  "folder": "M10,4H4C2.89,4 2,4.89 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V8C22,6.89 21.1,6 20,6H12L10,4Z",
  "folder-music": "M20,6H12L10,4H4A2,2 0 0,0 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V8A2,2 0 0,0 20,6M16,10V12H14V15A2,2 0 0,1 12,17A2,2 0 0,1 10,15A2,2 0 0,1 12,13C12.35,13 12.69,13.1 13,13.27V10H16Z",
  "chevron-right": "M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z",
  "chevron-up": "M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z",
  "chevron-left": "M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z",
  "music-note": "M12,3V13.55C11.41,13.21 10.73,13 10,13A4,4 0 0,0 6,17A4,4 0 0,0 10,21A4,4 0 0,0 14,17V7H18V3H12Z",
  "menu": "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z",
  "format-list-bulleted": "M7,5H21V7H7V5M7,13V11H21V13H7M4,4.5A1.5,1.5 0 0,1 5.5,6A1.5,1.5 0 0,1 4,7.5A1.5,1.5 0 0,1 2.5,6A1.5,1.5 0 0,1 4,4.5M4,10.5A1.5,1.5 0 0,1 5.5,12A1.5,1.5 0 0,1 4,13.5A1.5,1.5 0 0,1 2.5,12A1.5,1.5 0 0,1 4,10.5M7,19V17H21V19H7M4,16.5A1.5,1.5 0 0,1 5.5,18A1.5,1.5 0 0,1 4,19.5A1.5,1.5 0 0,1 2.5,18A1.5,1.5 0 0,1 4,16.5Z",
  "download": "M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z",
  "movie": "M18,4L20,8H17L15,4H13L15,8H12L10,4H8L10,8H7L5,4H4A2,2 0 0,0 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V4H18Z",
  "image": "M8.5,13.5L11,16.5L14.5,12L19,18H5M21,19V5C21,3.89 20.1,3 19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19Z",
};
const ALIAS = {"shield-lock": "shield-check", "shield-moon": "shield-home", "shield-off": "shield-search", "shield-alert": "shield-search", "shield-sync": "shield-search", "music": "music-note", "gesture-tap-button": "gesture-tap", "molecule-co2": "gauge", "window-shutter": "blinds", "window-shutter-open": "blinds-open", "air-humidifier": "water-percent", "audio-video": "television", "package-up": "package-variant", "package-check": "package-variant", "brightness-5": "brightness-6", "brightness-7": "brightness-6", "checkbox-marked-circle": "check-circle", "radiobox-blank": "check-circle-outline", "weather-snowy": "weather-cloudy", "weather-pouring": "weather-rainy", "weather-fog": "weather-cloudy", "weather-lightning": "weather-rainy", "lock-alert": "lock", "lock-clock": "lock", "lightbulb-group": "lightbulb-group", "current-ac": "flash", "sine-wave": "pulse", "cash": "gauge", "garage-open": "garage-open", "video": "camera", "playlist-music": "music-note", "album": "music-note", "account-music": "account", "radio": "music-note", "podcast": "microphone", "apps": "tune", "folder-music": "folder-music"};
class HaIcon extends HTMLElement {
  static get observedAttributes() { return ["icon"]; }
  connectedCallback() { if (!this.shadowRoot) this.attachShadow({mode: "open"}).innerHTML = `<style>:host{display:inline-flex;width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);vertical-align:middle}svg{width:100%;height:100%;fill:currentColor}</style><svg viewBox="0 0 24 24" aria-hidden="true"><path></path></svg>`; this.attributeChangedCallback(); }
  attributeChangedCallback() {
    if (!this.shadowRoot) return;
    let n = (this.getAttribute("icon") || "").replace(/^mdi:/, ""); const M0 = (typeof HL !== "undefined" && HL.MDI) || {}; if (!M0[n] && !EXTRA[n] && ALIAS[n]) n = ALIAS[n]; const M = (typeof HL !== "undefined" && HL.MDI) || {};
    const d = M[n] || EXTRA[n] || M[n.replace(/-off$/, "")] || M[n.replace(/-(outline|variant|off)$/, "")] || EXTRA[n.replace(/-(outline|variant|off)$/, "")] || M["help-circle"] || "M12,2A10,10 0 1,0 22,12A10,10 0 0,0 12,2Z";
    this.shadowRoot.querySelector("path").setAttribute("d", d);
  }
}
if (!customElements.get("ha-icon")) customElements.define("ha-icon", HaIcon);

/* art */
const svg = (a, b, glyph) => "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs><rect width="200" height="200" fill="url(#g)"/>${glyph || ""}</svg>`);
const circle = (x, y, r, o) => `<circle cx="${x}" cy="${y}" r="${r}" fill="#fff" fill-opacity="${o}"/>`;
const ART = svg("#7c4dff", "#ff4081", circle(70, 120, 70, .18) + circle(140, 70, 44, .22) + circle(110, 150, 26, .3));
const AVATAR = svg("#26a69a", "#00796b", `<circle cx="100" cy="78" r="38" fill="#fff" fill-opacity=".85"/><path d="M30 190c4-44 36-62 70-62s66 18 70 62z" fill="#fff" fill-opacity=".85"/>`);
const CAM = svg("#37474f", "#78909c", `<rect x="0" y="130" width="200" height="70" fill="#263238" fill-opacity=".6"/><rect x="40" y="70" width="60" height="70" fill="#fff" fill-opacity=".25"/><circle cx="150" cy="50" r="18" fill="#ffd54f" fill-opacity=".8"/>`);
const palette = [["#ef5350", "#ab47bc"], ["#42a5f5", "#26c6da"], ["#66bb6a", "#d4e157"], ["#ffa726", "#ff7043"], ["#5c6bc0", "#7e57c2"], ["#26a69a", "#9ccc65"]];
const thumb = i => svg(palette[i % 6][0], palette[i % 6][1], circle(60 + (i * 37) % 90, 100, 50 + (i * 11) % 30, .2) + circle(150, 60 + (i * 23) % 80, 30, .25));

/* states */
const now = new Date(Date.now() - 36e5 * 2).toISOString();
const S = {};
const E = (id, state, a = {}) => { S[id] = {entity_id: id, state, attributes: {friendly_name: id.split(".")[1].replace(/_/g, " ").replace(/^./, c => c.toUpperCase()), ...a}, last_changed: now, last_updated: now}; };
const hs2rgb = (h, s) => { s /= 100; const f = n => { const k = (n + h / 60) % 6; return Math.round(255 * (1 - s * Math.max(0, Math.min(k, 4 - k, 1)))); }; return [f(5), f(3), f(1)]; };
E("light.living_room", "on", {friendly_name: "Living room", supported_color_modes: ["color_temp", "hs"], color_mode: "color_temp", brightness: 191, color_temp_kelvin: 3200, min_color_temp_kelvin: 2000, max_color_temp_kelvin: 6500, hs_color: [32, 62], rgb_color: [255, 190, 120]});
E("light.kitchen", "on", {friendly_name: "Kitchen", supported_color_modes: ["brightness"], brightness: 120});
E("light.bedroom", "off", {friendly_name: "Bedroom", supported_color_modes: ["color_temp", "hs"], min_color_temp_kelvin: 2000, max_color_temp_kelvin: 6500});
E("light.desk", "on", {friendly_name: "Desk strip", supported_color_modes: ["hs"], brightness: 230, hs_color: [270, 80], rgb_color: [145, 50, 255]});
E("switch.coffee_machine", "on", {friendly_name: "Coffee machine", device_class: "outlet"});
E("input_boolean.guest_mode", "off", {friendly_name: "Guest mode"});
E("fan.bedroom", "on", {friendly_name: "Bedroom fan", supported_features: 57, percentage: 60, percentage_step: 20, preset_modes: ["auto", "sleep", "turbo"], preset_mode: "auto"});
E("humidifier.dehumidifier", "on", {friendly_name: "Dehumidifier", humidity: 45, current_humidity: 52, min_humidity: 30, max_humidity: 80});
E("cover.blinds", "open", {friendly_name: "Living room blinds", device_class: "blind", supported_features: 15, current_position: 70});
E("cover.garage", "closed", {friendly_name: "Garage door", device_class: "garage", supported_features: 3});
E("climate.living_room", "heat", {friendly_name: "Living room", hvac_modes: ["off", "heat", "cool", "auto"], hvac_action: "heating", temperature: 22, current_temperature: 20.5, min_temp: 7, max_temp: 30, target_temp_step: 0.5});
E("lock.front_door", "locked", {friendly_name: "Front door"});
E("vacuum.robot", "cleaning", {friendly_name: "Robot vacuum", supported_features: 12244, battery_level: 64});
E("alarm_control_panel.home", "disarmed", {friendly_name: "Home alarm", supported_features: 7});
E("sensor.living_temperature", "21.4", {friendly_name: "Living temperature", device_class: "temperature", unit_of_measurement: "°C", state_class: "measurement"});
E("sensor.living_humidity", "48", {friendly_name: "Living humidity", device_class: "humidity", unit_of_measurement: "%"});
E("sensor.power", "842", {friendly_name: "House power", device_class: "power", unit_of_measurement: "W"});
E("sensor.energy_today", "7.42", {friendly_name: "Energy today", device_class: "energy", unit_of_measurement: "kWh"});
E("sensor.outside_temperature", "8.6", {friendly_name: "Outside", device_class: "temperature", unit_of_measurement: "°C"});
E("sensor.phone_battery", "14", {friendly_name: "Phone battery", device_class: "battery", unit_of_measurement: "%"});
E("sensor.tablet_battery", "82", {friendly_name: "Tablet battery", device_class: "battery", unit_of_measurement: "%"});
E("binary_sensor.front_door", "on", {friendly_name: "Front door sensor", device_class: "door"});
E("binary_sensor.hall_motion", "off", {friendly_name: "Hall motion", device_class: "motion"});
E("weather.home", "partlycloudy", {friendly_name: "Home", temperature: 19, temperature_unit: "°C", humidity: 61, wind_speed: 14, wind_speed_unit: "km/h", pressure: 1014, pressure_unit: "hPa"});
E("person.teodor", "home", {friendly_name: "Teodor", entity_picture: AVATAR});
E("person.ola", "not_home", {friendly_name: "Ola"});
E("button.doorbell", "unknown", {friendly_name: "Ring doorbell chime"});
E("scene.movie_night", "scening", {friendly_name: "Movie night"});
E("script.good_night", "off", {friendly_name: "Good night"});
E("automation.lights_at_sunset", "on", {friendly_name: "Lights at sunset"});
E("media_player.living_room", "playing", {friendly_name: "Living room speaker", supported_features: 150463, media_title: "Midnight City", media_artist: "M83", media_album_name: "Hurry Up, We're Dreaming", entity_picture: ART, media_duration: 243, media_position: 71, media_position_updated_at: new Date().toISOString(), volume_level: 0.35, is_volume_muted: false, source: "Spotify", source_list: ["Spotify", "Line in", "Radio", "QNAP"], group_members: ["media_player.living_room"]});
E("media_player.kitchen", "idle", {friendly_name: "Kitchen", supported_features: 150463, group_members: []});
E("media_player.bedroom", "idle", {friendly_name: "Bedroom", supported_features: 150463, group_members: []});
E("media_player.tv", "off", {friendly_name: "TV", device_class: "tv", supported_features: 150463});
E("update.home_assistant_core", "on", {friendly_name: "Home Assistant Core", installed_version: "2025.9.3", latest_version: "2025.10.0", supported_features: 1});
E("camera.front_door", "idle", {friendly_name: "Front door camera", entity_picture: CAM});
E("timer.pizza", "active", {friendly_name: "Pizza", duration: "0:20:00", finishes_at: new Date(Date.now() + 612e3).toISOString()});
E("select.heating_mode", "Comfort", {friendly_name: "Heating mode", options: ["Eco", "Comfort", "Away"]});
E("number.target_soc", "80", {friendly_name: "Battery target", min: 20, max: 100, step: 5, unit_of_measurement: "%"});
E("sensor.unavailable_thing", "unavailable", {friendly_name: "Broken sensor", device_class: "temperature", unit_of_measurement: "°C"});

const areas = {living_room: {area_id: "living_room", name: "Living room", icon: "mdi:sofa"}};
const entities = {};
["light.living_room", "light.desk", "sensor.living_temperature", "sensor.living_humidity", "switch.coffee_machine", "fan.bedroom", "cover.blinds", "climate.living_room", "media_player.living_room", "lock.front_door", "scene.movie_night"].forEach(id => { entities[id] = {entity_id: id, area_id: "living_room"}; });
const hass = {states: S, areas, entities, devices: {}, user: {name: "Teodor Nowak", is_admin: true}, language: "en", locale: {language: (navigator.language || "en").slice(0, 2)}, config: {unit_system: {temperature: "°C"}}, themes: {}, hassUrl: p => p};

function broadcast() { for (const c of MOCK.cards) c.hass = MOCK.hass; }
function patch(id, state, attrs) { const o = S[id]; if (!o) return; const n = {...o, state: state ?? o.state, attributes: {...o.attributes, ...(attrs || {})}, last_updated: new Date().toISOString()}; if (state != null && state !== o.state) n.last_changed = n.last_updated; MOCK.states = {...MOCK.states, [id]: n}; MOCK.hass = {...MOCK.hass, states: MOCK.states}; }
MOCK.states = S; MOCK.hass = hass;

const tracks = [["Midnight City", "M83"], ["Intro", "The xx"], ["Instant Crush", "Daft Punk"], ["Genesis", "Justice"], ["Digital Love", "Daft Punk"]];
let ti = 0;
const lightColors = {};
MOCK.callService = (d, s, data = {}, target) => {
  MOCK.calls.push([d, s, data, target]);
  const ids = arr(data.entity_id).concat(arr(target && target.entity_id));
  const toast = () => window.dispatchEvent(new CustomEvent("mock-call", {detail: {d, s, data, target}}));
  for (const id of ids) {
    const st = S[id] && MOCK.states[id]; if (!st) continue; const a = st.attributes, dm = id.split(".")[0], key = `${d}.${s}`;
    if (d === "light" && s === "turn_on") {
      const p = {}; if (data.brightness_pct != null) p.brightness = Math.round(data.brightness_pct * 2.55); else if (st.state === "off") p.brightness = a.brightness || 200;
      if (data.color_temp_kelvin) { p.color_temp_kelvin = data.color_temp_kelvin; const k = data.color_temp_kelvin; p.rgb_color = k < 3500 ? [255, 190, 120] : k < 5000 ? [255, 235, 215] : [200, 220, 255]; p.hs_color = [30, 40]; }
      if (data.hs_color) { p.hs_color = data.hs_color; p.rgb_color = hs2rgb(...data.hs_color); }
      patch(id, "on", p);
    } else if ((d === "homeassistant" || d === dm) && (s === "turn_off" || s === "turn_on" || s === "toggle")) {
      const on = s === "toggle" ? !["on", "open", "unlocked"].includes(st.state) : s === "turn_on";
      patch(id, dm === "cover" ? (on ? "open" : "closed") : on ? "on" : "off");
    } else if (key === "cover.open_cover") patch(id, "open", {current_position: 100});
    else if (key === "cover.close_cover") patch(id, "closed", {current_position: 0});
    else if (key === "cover.toggle") patch(id, st.state === "closed" ? "open" : "closed", {current_position: st.state === "closed" ? 100 : 0});
    else if (key === "cover.set_cover_position") patch(id, data.position > 0 ? "open" : "closed", {current_position: data.position});
    else if (key === "climate.set_temperature") patch(id, null, {temperature: data.temperature});
    else if (key === "climate.set_hvac_mode") patch(id, data.hvac_mode, {hvac_action: data.hvac_mode === "off" ? "off" : data.hvac_mode === "cool" ? "cooling" : data.hvac_mode === "heat" ? "heating" : "idle"});
    else if (key === "fan.set_percentage") patch(id, "on", {percentage: data.percentage});
    else if (key === "fan.set_preset_mode") patch(id, null, {preset_mode: data.preset_mode});
    else if (key === "humidifier.set_humidity") patch(id, null, {humidity: data.humidity});
    else if (key === "lock.lock") patch(id, "locked"); else if (key === "lock.unlock") patch(id, "unlocked");
    else if (key === "vacuum.start") patch(id, "cleaning"); else if (key === "vacuum.pause" || key === "vacuum.stop") patch(id, "paused"); else if (key === "vacuum.return_to_base") patch(id, "returning");
    else if (d === "alarm_control_panel") patch(id, s === "alarm_disarm" ? "disarmed" : s.replace("alarm_arm_", "armed_"));
    else if (key === "media_player.media_play_pause") patch(id, st.state === "playing" ? "paused" : "playing", {media_position_updated_at: new Date().toISOString()});
    else if (key === "media_player.turn_on") patch(id, "idle");
    else if (key === "media_player.media_next_track" || key === "media_player.media_previous_track") { ti = (ti + (s.includes("next") ? 1 : tracks.length - 1)) % tracks.length; patch(id, null, {media_title: tracks[ti][0], media_artist: tracks[ti][1], media_position: 0, media_position_updated_at: new Date().toISOString(), entity_picture: thumb(ti + 1)}); }
    else if (key === "media_player.volume_set") patch(id, null, {volume_level: data.volume_level});
    else if (key === "media_player.volume_mute") patch(id, null, {is_volume_muted: data.is_volume_muted});
    else if (key === "media_player.select_source") patch(id, null, {source: data.source});
    else if (key === "media_player.media_seek") patch(id, null, {media_position: data.seek_position, media_position_updated_at: new Date().toISOString()});
    else if (key === "media_player.play_media") patch(id, "playing", {media_title: String(data.media_content_id).split("/").pop().replace(/\.\w+$/, "") || "Track", media_artist: "QNAP library", media_position: 0, media_duration: 200, media_position_updated_at: new Date().toISOString(), entity_picture: thumb(3)});
    else if (key === "media_player.join") patch(id, null, {group_members: [id, ...arr(data.group_members)].filter((v, i, x) => x.indexOf(v) === i)});
    else if (key === "media_player.unjoin") { const lead = Object.keys(S).find(k => k.startsWith("media_player.") && MOCK.states[k].attributes.group_members.includes(id) && k !== id); if (lead) patch(lead, null, {group_members: MOCK.states[lead].attributes.group_members.filter(x => x !== id)}); }
    else if (key === "select.select_option") patch(id, data.option);
    else if (key === "number.set_value") patch(id, String(data.value));
    else if (key === "timer.pause") patch(id, "paused", {remaining: "0:08:12"});
    else if (key === "timer.start") patch(id, "active", {finishes_at: new Date(Date.now() + 492e3).toISOString()});
    else if (key === "timer.cancel") patch(id, "idle");
    else if (key === "update.install") patch(id, "off", {installed_version: a.latest_version});
    else if (key === "script.turn_on") { patch(id, "on"); setTimeout(() => { patch(id, "off"); broadcast(); }, 1800); }
  }
  broadcast(); toast();
  return Promise.resolve();
};
const arr = v => v == null ? [] : Array.isArray(v) ? v : [v];
const dir = (title, id, n = 0) => ({title, media_class: "directory", media_content_type: "directory", media_content_id: id, can_play: false, can_expand: true, thumbnail: n ? thumb(n) : null});
const item = (title, id, n, cls = "music") => ({title, media_class: cls, media_content_type: cls === "music" ? "audio/mpeg" : "video/mp4", media_content_id: id, can_play: true, can_expand: false, thumbnail: thumb(n)});
const TREE = {
  "media-source://media_source": {title: "Media", children: [dir("QNAP", "media-source://media_source/qnap", 1), dir("Local media", "media-source://media_source/local", 4)]},
  "media-source://media_source/qnap": {title: "QNAP", children: [dir("Music", "media-source://media_source/qnap/Music", 2), dir("Movies", "media-source://media_source/qnap/Movies", 3), dir("Photos", "media-source://media_source/qnap/Photos", 5), dir("Podcasts", "media-source://media_source/qnap/Podcasts", 0)]},
  "media-source://media_source/qnap/Music": {title: "Music", children: ["Daft Punk", "M83", "The xx", "Justice", "Boards of Canada", "Air", "Röyksopp", "Massive Attack"].map((t, i) => dir(t, "media-source://media_source/qnap/Music/" + t, i + 1))},
  "media-source://media_source/qnap/Movies": {title: "Movies", children: ["Blade Runner.mp4", "Arrival.mp4", "Dune.mp4", "Her.mp4", "Drive.mp4"].map((t, i) => item(t.replace(".mp4", ""), "media-source://media_source/qnap/Movies/" + t, i + 3, "video"))},
};
for (const a of ["Daft Punk", "M83", "The xx", "Justice", "Boards of Canada", "Air", "Röyksopp", "Massive Attack"]) TREE["media-source://media_source/qnap/Music/" + a] = {title: a, can_play: true, children: ["Track one", "Track two", "Track three", "Track four", "Track five", "Track six"].map((t, i) => item(a + " - " + t, `media-source://media_source/qnap/Music/${a}/${t}.mp3`, i + a.length))};
const hist = id => {
  let seed = 0; for (const c of id) seed = (seed * 31 + c.charCodeAt(0)) % 997;
  const v = parseFloat(S[id] && S[id].state) || 10, out = [], t0 = Date.now() / 1000 - 86400;
  for (let i = 0; i < 90; i++) out.push({s: String(+(v * (1 + 0.18 * Math.sin(i / 9 + seed) + 0.08 * Math.sin(i / 2.3 + seed * 2))).toFixed(2)), lu: t0 + i * 960});
  return out;
};
MOCK.callWS = msg => new Promise((res, rej) => {
  setTimeout(() => {
    if (msg.type === "history/history_during_period") return res(Object.fromEntries(msg.entity_ids.map(i => [i, hist(i)])));
    if (msg.type === "media_player/browse_media") { const n = TREE[msg.media_content_id]; return n ? res({media_class: "directory", media_content_type: "directory", media_content_id: msg.media_content_id, can_play: false, can_expand: true, ...n}) : rej({code: "not_found", message: "Media not found"}); }
    rej({code: "unknown_command", message: msg.type});
  }, 120);
});
hass.callService = MOCK.callService; hass.callWS = MOCK.callWS;
Object.defineProperty(MOCK, "hass", {get() { return MOCK._h; }, set(v) { v.callService = MOCK.callService; v.callWS = MOCK.callWS; MOCK._h = v; }});
MOCK.hass = hass;
})();
