"""Provider-neutral tool layer: schemas, server-side policy, staging/approval, config edits with backups, audit log.
By TeodorTeo.com (https://teodorteo.com)."""
import asyncio
import difflib
import fnmatch
import json
import re
import statistics
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ha import HA, HAError

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
DOMAIN_RE = re.compile(r"^[a-z0-9_]+$")
CID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
SVC_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
CKINDS = ("automation", "script", "scene")
MAX_SEARCH = 40
AUDIT_MAX = 1024 * 1024
SAFE_READONLY = {"homeassistant.update_entity", "weather.get_forecasts", "calendar.get_events"}
SECRET_RE = re.compile(r"^(\s*[\w\-]*(?:password|token|secret|api_key|apikey|key|passwd|credentials?)[\w\-]*\s*:\s*)(?!!secret)(\S.*)$", re.I)
CONFIG_FILES_OK = re.compile(r"^(?!secrets)[\w\-./]+\.ya?ml$")


class ToolError(Exception):
    pass


def fold(s):
    s = unicodedata.normalize("NFKD", str(s).lower().replace("ł", "l"))
    return "".join(c for c in s if not unicodedata.combining(c))


def clip(obj, n=6000):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    return s if len(s) <= n else s[:n] + f'... [truncated, {len(s) - n} more chars]'


def S(type_, desc="", **kw):
    return {"type": type_, "description": desc, **kw}


def spec(name, desc, props=None, required=(), write=False):
    return {"name": name, "description": desc, "write": write,
            "parameters": {"type": "object", "properties": props or {}, "required": list(required)}}


SPECS = [
    spec("search_entities", "Find entities by free text (name, entity_id, area). ALWAYS use this before guessing an entity_id. Max 40 results.",
         {"query": S("string", "words to look for, e.g. 'kitchen light'"), "domain": S("string", "optional domain filter, e.g. light"),
          "area": S("string", "optional area name")}, ["query"]),
    spec("get_state", "Get the current state and attributes of one entity.", {"entity_id": S("string")}, ["entity_id"]),
    spec("get_states_summary", "Without domain: entity counts per domain. With domain: compact list of 'entity_id: state'.", {"domain": S("string")}),
    spec("list_areas", "List areas (rooms) with entity counts."),
    spec("list_devices", "List devices, optionally only those in an area.", {"area": S("string", "area name or id")}),
    spec("call_service", "Call a Home Assistant service to CONTROL devices (turn on/off, set temperature...). Depending on the mode this may be executed immediately or staged for the user's approval - check the result status.",
         {"domain": S("string", "e.g. light"), "service": S("string", "e.g. turn_on"),
          "data": S("object", "service data, e.g. {\"brightness_pct\": 50}"),
          "target": S("object", "target, e.g. {\"entity_id\": [\"light.kitchen\"]}")}, ["domain", "service"], write=True),
    spec("get_history", "Recent state history of one entity (compressed, with min/max/mean for numeric states).",
         {"entity_id": S("string"), "hours": S("integer", "1-168, default 24")}, ["entity_id"]),
    spec("render_template", "Render a Home Assistant Jinja template (read-only), e.g. {{ states('sensor.x') }}.", {"template": S("string")}, ["template"]),
    spec("list_automations", "List automations (entity_id, config id, alias, state, last_triggered)."),
    spec("get_automation", "Get the full configuration of an automation by its config id.", {"id": S("string")}, ["id"]),
    spec("list_scripts", "List scripts (id, alias, state)."),
    spec("get_script", "Get the full configuration of a script by id.", {"id": S("string")}, ["id"]),
    spec("list_scenes", "List scenes (entity_id, config id, name)."),
    spec("get_scene", "Get the full configuration of a UI-defined scene by id.", {"id": S("string")}, ["id"]),
    spec("read_config_file", "Read a YAML file of the Home Assistant config folder for context (read-only; secrets are hidden). E.g. configuration.yaml, automations.yaml.",
         {"path": S("string", "relative path, e.g. packages/lights.yaml"), "offset": S("integer", "character offset")}, ["path"]),
    spec("propose_automation", "Propose creating (no id) or updating (id) an automation. NOT applied: the user sees a diff and must approve. config needs alias, triggers, actions (and optional conditions, mode).",
         {"id": S("string", "existing config id to update; omit to create"), "config": S("object", "full automation config"),
          "reason": S("string", "why, in one sentence")}, ["config", "reason"], write=True),
    spec("propose_script", "Propose creating or updating a script (id = object id, e.g. night_routine). NOT applied until the user approves. config needs sequence.",
         {"id": S("string", "script id (snake_case)"), "config": S("object", "full script config"), "reason": S("string")}, ["id", "config", "reason"], write=True),
    spec("propose_scene", "Propose creating or updating a scene. NOT applied until the user approves. config needs name and entities (map entity_id -> state/attributes).",
         {"id": S("string", "existing id to update; omit to create"), "config": S("object", "full scene config"), "reason": S("string")}, ["config", "reason"], write=True),
    spec("propose_delete", "Propose deleting an automation, script or scene. NOT applied until the user approves.",
         {"kind": S("string", "automation|script|scene", enum=list(CKINDS)), "id": S("string"), "reason": S("string")}, ["kind", "id", "reason"], write=True),
]
SPEC_BY_NAME = {s["name"]: s for s in SPECS}


def public_specs(mode):
    return [{k: v for k, v in s.items() if k != "write"} for s in SPECS if not (mode == "read_only" and s["write"])]


def coerce_args(name, args):
    """Models (esp. Gemini) may send JSON objects as strings; parse them back according to the schema."""
    sp = SPEC_BY_NAME[name]["parameters"]["properties"]
    out = {}
    for k, v in args.items():
        t = (sp.get(k) or {}).get("type")
        if t == "object" and isinstance(v, str):
            try:
                v = json.loads(v) if v.strip() else {}
            except ValueError:
                raise ToolError(f"argument '{k}' must be a JSON object")
        if t == "integer" and isinstance(v, (str, float)):
            try:
                v = int(float(v))
            except ValueError:
                raise ToolError(f"argument '{k}' must be an integer")
        out[k] = v
    return out


def need_str(args, k, rx=None, optional=False):
    v = args.get(k)
    if v is None or v == "":
        if optional:
            return None
        raise ToolError(f"missing argument '{k}'")
    if not isinstance(v, str):
        raise ToolError(f"argument '{k}' must be a string")
    if rx and not rx.match(v):
        raise ToolError(f"invalid value for '{k}': {v[:60]!r}")
    return v


def eid_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return v
    raise ToolError("entity_id must be a string or a list of strings")


def small_attrs(attrs):
    out = {}
    for k, v in (attrs or {}).items():
        if isinstance(v, str) and len(v) > 200:
            v = v[:200] + "..."
        elif isinstance(v, (list, dict)) and len(json.dumps(v, default=str)) > 300:
            v = clip(v, 300)
        out[k] = v
    return out


class Tools:
    def __init__(self, ha: HA, opts, data_dir: Path, config_dir: Path, tzname_fn, on_update):
        self.ha, self.opts, self.config_dir = ha, opts, config_dir
        self.audit_file, self.backup_dir = data_dir / "audit.jsonl", data_dir / "backups"
        self.pending = {}          # id -> item (same objects live in conversation timelines)
        self.on_update = on_update  # callback(conv_id, item, note) after a pending item changes
        self.tzname = tzname_fn

    # ------------------------------------------------------------ audit
    def audit(self, conv_id, tool, args, outcome, approved_by="-", result=""):
        try:
            self.audit_file.parent.mkdir(parents=True, exist_ok=True)
            if self.audit_file.exists() and self.audit_file.stat().st_size > AUDIT_MAX:
                self.audit_file.replace(self.audit_file.with_suffix(".jsonl.1"))
            with self.audit_file.open("a") as f:
                f.write(json.dumps({"ts": time.time(), "conv": conv_id, "tool": tool, "args": clip(args, 600), "outcome": outcome,
                                    "by": approved_by, "result": clip(result, 400)}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def read_audit(self, limit=200):
        rows = []
        for p in (self.audit_file.with_suffix(".jsonl.1"), self.audit_file):
            try:
                rows += [json.loads(x) for x in p.read_text().splitlines()[-limit:] if x.strip()]
            except (OSError, ValueError):
                pass
        return rows[-limit:][::-1]

    # ------------------------------------------------------------ policy
    def blocked_check(self, domain, service, entity_ids, target_keys=()):
        o = self.opts
        if domain in (o.blocked_domains or []):
            raise ToolError(f"BLOCKED: domain '{domain}' is on the blocked list; tell the user this is not allowed.")
        full = f"{domain}.{service}"
        for pat in o.blocked_services or []:
            if fnmatch.fnmatch(full, pat):
                raise ToolError(f"BLOCKED: service '{full}' is on the blocked list; tell the user this is not allowed.")
        for e in entity_ids:
            if e.split(".")[0] in (o.blocked_domains or []):
                raise ToolError(f"BLOCKED: entity '{e}' belongs to a blocked domain; tell the user this is not allowed.")
        if domain == "homeassistant" and target_keys:
            raise ToolError("BLOCKED: homeassistant.* services must list explicit entity_ids (no area/device/floor/label targets).")

    def is_readonly(self, full, resp_modes):
        return full in SAFE_READONLY or resp_modes.get(full) == "only"

    # ------------------------------------------------------------ dispatch
    async def execute(self, conv_id, name, args, stage):
        """Returns (content str, outcome, is_error). `stage(item)` registers a pending item in the conversation."""
        mode = self.opts.mode
        try:
            if name not in SPEC_BY_NAME:
                raise ToolError(f"unknown tool '{name}'")
            if not isinstance(args, dict) or "_invalid" in args:
                raise ToolError("arguments were not a valid JSON object")
            if SPEC_BY_NAME[name]["write"] and mode == "read_only" and name != "call_service":
                raise ToolError("mode is read_only: no changes can be proposed")
            args = coerce_args(name, args)
            res = await getattr(self, "t_" + name)(conv_id, args, stage)
            outcome = "staged" if isinstance(res, dict) and res.get("status") == "staged" else "ok"
            if isinstance(res, dict) and res.get("status") == "executed":
                outcome = "executed"
            self.audit(conv_id, name, args, outcome, "auto" if outcome == "executed" else "-", clip(res, 400))
            return clip(res), outcome, False
        except ToolError as e:
            outcome = "blocked" if str(e).startswith("BLOCKED") or "read_only" in str(e) else "error"
            self.audit(conv_id, name, args if isinstance(args, dict) else {}, outcome, "-", str(e))
            return clip({"error": str(e)}), outcome, True
        except HAError as e:
            self.audit(conv_id, name, args if isinstance(args, dict) else {}, "error", "-", str(e))
            return clip({"error": f"Home Assistant error {e.status}: {e}"}), "error", True
        except (asyncio.TimeoutError, TimeoutError):
            return clip({"error": "timeout"}), "error", True

    # ------------------------------------------------------------ read tools
    async def _areas(self):
        areas, devices, ents = await self.ha.registries()
        amap = {a["area_id"]: a.get("name", a["area_id"]) for a in areas if isinstance(a, dict) and "area_id" in a}
        dev_area = {d["id"]: d.get("area_id") for d in devices if isinstance(d, dict) and "id" in d}
        ent_area = {}
        for e in ents:
            if isinstance(e, dict) and e.get("entity_id"):
                aid = e.get("area_id") or dev_area.get(e.get("device_id"))
                if aid:
                    ent_area[e["entity_id"]] = amap.get(aid, aid)
        return amap, devices, ent_area

    async def t_search_entities(self, cid, a, stage):
        q = fold(need_str(a, "query"))
        dom = need_str(a, "domain", DOMAIN_RE, True)
        area = fold(need_str(a, "area", optional=True) or "")
        toks = [t for t in re.split(r"\s+", q) if t]
        amap, _, ent_area = await self._areas()
        scored = []
        for st in await self.ha.states():
            eid = st["entity_id"]
            if dom and not eid.startswith(dom + "."):
                continue
            ar = ent_area.get(eid, "")
            if area and area not in fold(ar):
                continue
            name = (st.get("attributes") or {}).get("friendly_name", "")
            hay = fold(f"{eid} {name} {ar}")
            sc = sum(1 for t in toks if t in hay)
            if toks and sc == 0:
                continue
            scored.append((sc, -len(eid), {"entity_id": eid, "name": name, "state": st["state"], "area": ar}))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best = scored[0][0] if scored else 0
        cand = [x[2] for x in scored if x[0] == best or not toks]
        return {"count": len(cand[:MAX_SEARCH]), "truncated": len(cand) > MAX_SEARCH, "entities": cand[:MAX_SEARCH]}

    async def t_get_state(self, cid, a, stage):
        eid = need_str(a, "entity_id", ENTITY_RE)
        st = await self.ha.state(eid)
        if st is None:
            raise ToolError(f"entity '{eid}' not found - use search_entities")
        return {"entity_id": eid, "state": st["state"], "attributes": small_attrs(st.get("attributes")), "last_changed": st.get("last_changed")}

    async def t_get_states_summary(self, cid, a, stage):
        dom = need_str(a, "domain", DOMAIN_RE, True)
        states = await self.ha.states()
        if not dom:
            c = {}
            for s in states:
                d = s["entity_id"].split(".")[0]
                c[d] = c.get(d, 0) + 1
            return {"domains": dict(sorted(c.items()))}
        rows = [f"{s['entity_id']}: {s['state']}" + (f" ({s['attributes']['friendly_name']})" if s.get("attributes", {}).get("friendly_name") else "")
                for s in states if s["entity_id"].startswith(dom + ".")]
        return {"count": len(rows), "entities": rows[:80], "truncated": len(rows) > 80}

    async def t_list_areas(self, cid, a, stage):
        amap, _, ent_area = await self._areas()
        cnt = {}
        for v in ent_area.values():
            cnt[v] = cnt.get(v, 0) + 1
        return {"areas": [{"area_id": k, "name": v, "entities": cnt.get(v, 0)} for k, v in amap.items()][:80]}

    async def t_list_devices(self, cid, a, stage):
        area = fold(need_str(a, "area", optional=True) or "")
        amap, devices, _ = await self._areas()
        out = []
        for d in devices:
            ar = amap.get(d.get("area_id"), "")
            if area and area not in fold(ar + " " + str(d.get("area_id") or "")):
                continue
            out.append({"id": d.get("id"), "name": d.get("name_by_user") or d.get("name"), "area": ar,
                        "manufacturer": d.get("manufacturer"), "model": d.get("model")})
        return {"count": len(out), "devices": out[:60], "truncated": len(out) > 60}

    async def t_get_history(self, cid, a, stage):
        eid = need_str(a, "entity_id", ENTITY_RE)
        hours = max(1, min(168, int(a.get("hours") or 24)))
        start = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        data = await self.ha.req("GET", f"/history/period/{start}", params={"filter_entity_id": eid, "minimal_response": "1", "no_attributes": "1"},
                                 timeout=30, limit=6 * 1024 * 1024)
        rows = data[0] if isinstance(data, list) and data else []
        pts = [(r.get("last_changed") or r.get("last_updated"), r.get("state")) for r in rows if isinstance(r, dict)]
        res = {"entity_id": eid, "hours": hours, "changes": len(pts)}
        nums = []
        for _, s in pts:
            try:
                nums.append(float(s))
            except (TypeError, ValueError):
                pass
        if len(nums) > 1:
            res.update(min=min(nums), max=max(nums), mean=round(statistics.fmean(nums), 3))
        if len(pts) > 40:
            step = len(pts) / 40
            pts = [pts[int(i * step)] for i in range(40)] + [pts[-1]]
            res["downsampled"] = True
        res["points"] = [[(t or "")[:19], s] for t, s in pts]
        return res

    async def t_render_template(self, cid, a, stage):
        t = need_str(a, "template")
        if len(t) > 2000:
            raise ToolError("template too long (max 2000 chars)")
        r = await self.ha.req("POST", "/template", {"template": t}, timeout=15, limit=512 * 1024)
        return {"result": clip(r if isinstance(r, str) else json.dumps(r), 3000)}

    async def _list_domain(self, dom):
        return [s for s in await self.ha.states() if s["entity_id"].startswith(dom + ".")]

    async def t_list_automations(self, cid, a, stage):
        rows = [{"entity_id": s["entity_id"], "id": s["attributes"].get("id"), "alias": s["attributes"].get("friendly_name"), "state": s["state"],
                 "last_triggered": s["attributes"].get("last_triggered")} for s in await self._list_domain("automation")]
        return {"count": len(rows), "automations": rows[:100], "truncated": len(rows) > 100}

    async def t_list_scripts(self, cid, a, stage):
        rows = [{"entity_id": s["entity_id"], "id": s["entity_id"].split(".", 1)[1], "alias": s["attributes"].get("friendly_name"), "state": s["state"]}
                for s in await self._list_domain("script")]
        return {"count": len(rows), "scripts": rows[:100], "truncated": len(rows) > 100}

    async def t_list_scenes(self, cid, a, stage):
        rows = [{"entity_id": s["entity_id"], "id": s["attributes"].get("id"), "name": s["attributes"].get("friendly_name")} for s in await self._list_domain("scene")]
        return {"count": len(rows), "scenes": rows[:100], "truncated": len(rows) > 100}

    async def _get_cfg(self, kind, cid):
        return await self.ha.req("GET", f"/config/{kind}/config/{cid}", ok404=True)

    async def _t_get(self, kind, a):
        i = need_str(a, "id", CID_RE)
        c = await self._get_cfg(kind, i)
        if c is None:
            raise ToolError(f"{kind} '{i}' not found (use the config id from list_{kind}s)")
        return {"id": i, "config": c}

    async def t_get_automation(self, cid, a, stage):
        return await self._t_get("automation", a)

    async def t_get_script(self, cid, a, stage):
        return await self._t_get("script", a)

    async def t_get_scene(self, cid, a, stage):
        return await self._t_get("scene", a)

    async def t_read_config_file(self, cid, a, stage):
        rel = need_str(a, "path")
        if ".." in rel.split("/") or rel.startswith("/") or not CONFIG_FILES_OK.match(rel) or rel.startswith(".storage") or "/." in rel:
            raise ToolError("path not allowed (relative .yaml files only; secrets are never readable)")
        root = self.config_dir.resolve()
        p = (root / rel).resolve()
        if root not in p.parents or not p.is_file():
            raise ToolError("file not found")
        off = max(0, int(a.get("offset") or 0))
        with p.open("r", errors="replace") as f:
            f.seek(0)
            text = f.read(off + 12001)[off:]
        more = len(text) > 12000
        text = "\n".join(SECRET_RE.sub(r"\1<hidden>", ln) for ln in text[:12000].splitlines())
        return {"path": rel, "offset": off, "more": more, "content": text}

    # ------------------------------------------------------------ control
    async def t_call_service(self, cid, a, stage):
        dom = need_str(a, "domain", DOMAIN_RE)
        svc = need_str(a, "service", DOMAIN_RE)
        data, target = a.get("data") or {}, a.get("target") or {}
        if not isinstance(data, dict) or not isinstance(target, dict):
            raise ToolError("data and target must be objects")
        if len(json.dumps([data, target], default=str)) > 8000:
            raise ToolError("data too large")
        ids = eid_list(target.get("entity_id")) + eid_list(data.get("entity_id"))
        for e in ids:
            if e not in ("all", "none") and not ENTITY_RE.match(e):
                raise ToolError(f"invalid entity_id '{e[:60]}'")
        tkeys = [k for k in ("area_id", "device_id", "floor_id", "label_id") if target.get(k) or data.get(k)]
        self.blocked_check(dom, svc, [e for e in ids if e not in ("all", "none")], tkeys)
        full = f"{dom}.{svc}"
        names, resp = await self.ha.services()
        if names and full not in names:
            raise ToolError(f"service '{full}' does not exist")
        if "all" in ids and dom == "homeassistant":
            raise ToolError("BLOCKED: entity_id 'all' is not allowed with homeassistant.*")
        known = {s["entity_id"] for s in await self.ha.states()} if ids else set()
        miss = [e for e in ids if e not in known and e not in ("all", "none")]
        if miss:
            raise ToolError(f"unknown entity_id(s): {', '.join(miss[:5])} - use search_entities")
        ro = self.is_readonly(full, resp)
        if self.opts.mode == "read_only" and not ro:
            raise ToolError("mode is read_only: controlling devices is disabled")
        payload = {"domain": dom, "service": svc, "data": data, "target": target, "response": full in resp}
        if self.opts.mode == "auto" or ro:
            result = await self.run_service(payload)
            return {"status": "executed", "service": full, "result": result}
        names_s = ", ".join(ids[:6]) or "(no entity)"
        item = self.new_item("service", f"{full} -> {names_s}" + (f" {clip(data, 120)}" if data else ""), a.get("reason", ""), payload)
        item["diff"] = ""
        stage(item)
        return {"status": "staged", "pending_id": item["id"], "message": "NOT executed yet. The user must approve it in the panel. Do not claim it was done."}

    async def run_service(self, p):
        body = {**p["data"]}
        for k, v in p["target"].items():
            body.setdefault(k, v)
        params = {"return_response": "1"} if p.get("response") else None
        r = await self.ha.req("POST", f"/services/{p['domain']}/{p['service']}", body, params=params, timeout=30)
        if isinstance(r, dict) and "service_response" in r:
            return clip(r["service_response"], 2500)
        return f"ok ({len(r) if isinstance(r, list) else 0} entities changed)"

    # ------------------------------------------------------------ staged config changes
    def new_item(self, typ, title, reason, payload):
        item = {"kind": "pending", "id": uuid.uuid4().hex[:10], "type": typ, "title": title, "reason": str(reason or "")[:300],
                "status": "pending", "created": time.time(), "payload": payload, "diff": "", "result": "", "backup": ""}
        self.pending[item["id"]] = item
        return item

    async def validate(self, kind, cfg):
        if not isinstance(cfg, dict) or not cfg:
            raise ToolError("config must be a non-empty object")
        errs, warns = [], []
        if kind == "automation":
            if not (cfg.get("triggers") or cfg.get("trigger")):
                errs.append("missing 'triggers' (or 'trigger')")
            if not (cfg.get("actions") or cfg.get("action")):
                errs.append("missing 'actions' (or 'action')")
            if not cfg.get("alias"):
                errs.append("missing 'alias'")
        elif kind == "script":
            if not isinstance(cfg.get("sequence"), (list, dict)) or not cfg.get("sequence"):
                errs.append("missing 'sequence'")
        else:
            if not isinstance(cfg.get("entities"), dict) or not cfg.get("entities"):
                errs.append("missing 'entities' (object entity_id -> state)")
            if not cfg.get("name"):
                errs.append("missing 'name'")
        known = {s["entity_id"] for s in await self.ha.states()}
        names, _ = await self.ha.services()
        seen = set()

        def eids(v):
            return [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str) and "{{" not in x and x not in ("all", "none")]

        def walk(n, act):
            if isinstance(n, dict):
                svc = n.get("action") if isinstance(n.get("action"), str) else n.get("service")
                is_act = act or isinstance(svc, str)
                if isinstance(svc, str) and "{{" not in svc:
                    if not SVC_RE.match(svc):
                        errs.append(f"invalid service '{svc[:50]}'")
                    else:
                        try:
                            self.blocked_check(svc.split(".")[0], svc.split(".")[1], [])
                        except ToolError as e:
                            errs.append(str(e))
                        if names and svc not in names and svc not in seen:
                            errs.append(f"unknown service '{svc}'")
                        seen.add(svc)
                if kind == "scene" and n is cfg.get("entities"):
                    for k in n:
                        chk(k, True)
                for k, v in n.items():
                    if k == "entity_id":
                        for e in eids(v):
                            chk(e, is_act)
                    else:
                        walk(v, is_act)
            elif isinstance(n, list):
                for x in n:
                    walk(x, act)

        def chk(e, is_act):
            if not ENTITY_RE.match(e):
                errs.append(f"invalid entity_id '{e[:50]}'")
            elif e not in known:
                errs.append(f"unknown entity_id '{e}'")
            elif is_act and e.split(".")[0] in (self.opts.blocked_domains or []):
                errs.append(f"BLOCKED: entity '{e}' is in a blocked domain")
        walk(cfg, False)
        if kind == "scene":
            for e in cfg.get("entities", {}) if isinstance(cfg.get("entities"), dict) else []:
                if e.split(".")[0] in (self.opts.blocked_domains or []):
                    errs.append(f"BLOCKED: entity '{e}' is in a blocked domain")
        errs = list(dict.fromkeys(errs))
        if errs:
            raise ToolError("validation failed: " + "; ".join(errs[:10]))
        return warns

    @staticmethod
    def make_diff(old, new):
        a = json.dumps(old, indent=2, ensure_ascii=False, sort_keys=False).splitlines() if old is not None else []
        b = json.dumps(new, indent=2, ensure_ascii=False, sort_keys=False).splitlines() if new is not None else []
        d = list(difflib.unified_diff(a, b, "current", "proposed", lineterm="", n=3))
        return "\n".join(d[:300]) + ("\n... (diff truncated)" if len(d) > 300 else "")

    async def _propose(self, kind, cid_in, cfg, reason, stage):
        if self.opts.mode == "read_only":
            raise ToolError("mode is read_only: no changes can be proposed")
        if not isinstance(cfg, dict):
            raise ToolError("config must be an object")
        cfg = {k: v for k, v in cfg.items() if k != "id"} if kind != "automation" else dict(cfg)
        cid = cid_in or None
        if not cid:
            cid = str(int(time.time() * 1000)) if kind != "script" else None
        if kind == "script" and not cid:
            raise ToolError("script needs an id (snake_case)")
        if not CID_RE.match(cid):
            raise ToolError("invalid id")
        if kind == "automation":
            cfg["id"] = cid
        await self.validate(kind, cfg)
        cur = await self._get_cfg(kind, cid)
        if cid_in and cur is None and kind != "script":
            raise ToolError(f"{kind} '{cid}' does not exist - omit id to create a new one")
        title = f"{'Update' if cur is not None else 'Create'} {kind}: {cfg.get('alias') or cfg.get('name') or cid}"
        item = self.new_item("config", title, reason, {"ckind": kind, "cid": cid, "config": cfg, "existed": cur is not None})
        item["diff"] = self.make_diff(cur, cfg)
        stage(item)
        return {"status": "staged", "pending_id": item["id"], "message": "NOT applied. The user sees a diff and must press Approve in the panel. Do not claim it was applied."}

    async def t_propose_automation(self, cid, a, stage):
        return await self._propose("automation", need_str(a, "id", CID_RE, True), a.get("config"), a.get("reason"), stage)

    async def t_propose_script(self, cid, a, stage):
        return await self._propose("script", need_str(a, "id", CID_RE), a.get("config"), a.get("reason"), stage)

    async def t_propose_scene(self, cid, a, stage):
        return await self._propose("scene", need_str(a, "id", CID_RE, True), a.get("config"), a.get("reason"), stage)

    async def t_propose_delete(self, cid, a, stage):
        if self.opts.mode == "read_only":
            raise ToolError("mode is read_only: no changes can be proposed")
        kind = need_str(a, "kind")
        if kind not in CKINDS:
            raise ToolError("kind must be automation, script or scene")
        i = need_str(a, "id", CID_RE)
        cur = await self._get_cfg(kind, i)
        if cur is None:
            raise ToolError(f"{kind} '{i}' not found")
        item = self.new_item("delete", f"Delete {kind}: {(cur.get('alias') or cur.get('name') or i) if isinstance(cur, dict) else i}", a.get("reason"),
                             {"ckind": kind, "cid": i, "existed": True})
        item["diff"] = self.make_diff(cur, None)
        stage(item)
        return {"status": "staged", "pending_id": item["id"], "message": "NOT deleted. The user must approve in the panel."}

    # ------------------------------------------------------------ approval
    def _backup(self, kind, cid, prev):
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        p = self.backup_dir / f"{kind}_{cid}_{int(time.time())}.json"
        p.write_text(json.dumps({"kind": kind, "id": cid, "existed": prev is not None, "config": prev, "saved": time.time()}, ensure_ascii=False, indent=1))
        # keep the backup folder small
        files = sorted(self.backup_dir.glob("*.json"), key=lambda x: x.stat().st_mtime)
        for old in files[:-200]:
            old.unlink(missing_ok=True)
        return p.name

    async def _reload(self, kind):
        try:
            await self.ha.req("POST", f"/services/{kind}/reload", {}, timeout=20)
        except HAError:
            pass

    async def approve(self, pid, who="user"):
        item = self.pending.get(pid)
        if not item:
            raise ToolError("unknown pending change")
        if item["status"] != "pending":
            raise ToolError(f"already {item['status']}")
        p = item["payload"]
        try:
            if item["type"] == "service":
                if self.opts.mode == "read_only":
                    raise ToolError("mode is read_only")
                ids = eid_list(p["target"].get("entity_id")) + eid_list(p["data"].get("entity_id"))
                self.blocked_check(p["domain"], p["service"], [e for e in ids if e not in ("all", "none")],
                                   [k for k in ("area_id", "device_id", "floor_id", "label_id") if p["target"].get(k) or p["data"].get(k)])
                item["result"] = await self.run_service(p)
            else:
                if self.opts.mode == "read_only":
                    raise ToolError("mode is read_only")
                kind, cid = p["ckind"], p["cid"]
                if item["type"] == "config":
                    await self.validate(kind, p["config"])   # re-validate (policy may have changed)
                prev = await self._get_cfg(kind, cid)
                item["backup"] = self._backup(kind, cid, prev)
                if item["type"] == "config":
                    await self.ha.req("POST", f"/config/{kind}/config/{cid}", p["config"])
                else:
                    await self.ha.req("DELETE", f"/config/{kind}/config/{cid}")
                await self._reload(kind)
                item["result"] = "applied" if item["type"] == "config" else "deleted"
            item["status"] = "applied"
            item["by"] = who
            self.audit("", item["type"], {"title": item["title"], "payload": p}, "applied", who, item["result"])
            note = f"The user APPROVED the pending change '{item['title']}' and it was applied successfully ({item['result']})."
        except (ToolError, HAError) as e:
            item["status"] = "failed"
            item["result"] = str(e)[:300]
            self.audit("", item["type"], {"title": item["title"]}, "failed", who, str(e))
            note = f"The user approved '{item['title']}' but applying it FAILED: {item['result']}"
        item["updated"] = time.time()
        self.on_update(item, note)
        return item

    def reject(self, pid):
        item = self.pending.get(pid)
        if not item or item["status"] != "pending":
            raise ToolError("not pending")
        item["status"], item["updated"] = "rejected", time.time()
        self.audit("", item["type"], {"title": item["title"]}, "rejected", "user", "")
        self.on_update(item, f"The user REJECTED the pending change '{item['title']}'. It was not applied.")
        return item

    async def undo(self, pid):
        item = self.pending.get(pid)
        if not item or item["status"] != "applied" or not item.get("backup"):
            raise ToolError("nothing to undo")
        try:
            b = json.loads((self.backup_dir / Path(item["backup"]).name).read_text())
            kind, cid = b["kind"], b["id"]
            if b["existed"]:
                await self.ha.req("POST", f"/config/{kind}/config/{cid}", b["config"])
            else:
                await self.ha.req("DELETE", f"/config/{kind}/config/{cid}", ok404=True)
            await self._reload(kind)
        except (OSError, ValueError, HAError) as e:
            raise ToolError(f"undo failed: {e}")
        item["status"], item["updated"], item["result"] = "undone", time.time(), "previous configuration restored"
        self.audit("", "undo", {"title": item["title"], "backup": item["backup"]}, "undone", "user", "")
        self.on_update(item, f"The user UNDID the change '{item['title']}' (previous configuration restored).")
        return item
