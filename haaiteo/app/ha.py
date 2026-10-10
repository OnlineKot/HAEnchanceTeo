"""Thin Home Assistant client (REST + WebSocket) - aiohttp only, low memory: nothing big is cached.
By TeodorTeo.com (https://teodorteo.com)."""
import json
import time

from aiohttp import ClientTimeout, WSMsgType

MAX_BODY = 3 * 1024 * 1024  # hard cap for any HA/LLM response we read into memory


class HAError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


async def read_limited(resp, limit=MAX_BODY):
    """Stream-read a response body, refusing to hold more than `limit` bytes."""
    buf = bytearray()
    async for chunk in resp.content.iter_chunked(16384):
        buf += chunk
        if len(buf) > limit:
            raise HAError(502, "response too large")
    return bytes(buf)


class HA:
    def __init__(self, session, base, ws_url, token):
        self.s, self.base, self.ws_url, self.token = session, base.rstrip("/"), ws_url, token
        self._svc = (0, frozenset(), {})   # ts, names, readonly-info
        self._cfg = (0, {})

    def headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def req(self, method, path, body=None, params=None, ok404=False, timeout=20, limit=MAX_BODY):
        try:
            async with self.s.request(method, self.base + path, json=body, params=params, headers=self.headers(),
                                      timeout=ClientTimeout(total=timeout)) as r:
                raw = await read_limited(r, limit)
                if r.status == 404 and ok404:
                    return None
                txt = raw.decode("utf-8", "replace")
                if r.status >= 400:
                    try:
                        msg = json.loads(txt).get("message", txt)
                    except Exception:  # noqa: BLE001
                        msg = txt
                    raise HAError(r.status, str(msg)[:300])
                try:
                    return json.loads(txt)
                except ValueError:
                    return txt
        except HAError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HAError(502, f"Home Assistant unreachable: {type(exc).__name__}")

    async def states(self):
        return await self.req("GET", "/states", limit=8 * 1024 * 1024)

    async def state(self, eid):
        return await self.req("GET", f"/states/{eid}", ok404=True)

    async def config(self):
        if time.time() - self._cfg[0] > 600:
            try:
                self._cfg = (time.time(), await self.req("GET", "/config"))
            except HAError:
                return self._cfg[1]
        return self._cfg[1]

    async def services(self):
        """Returns (set of 'domain.service', {name: response_mode}); only names are kept in memory."""
        if time.time() - self._svc[0] > 300:
            data = await self.req("GET", "/services", limit=8 * 1024 * 1024)
            names, resp = set(), {}
            for d in data if isinstance(data, list) else []:
                for sname, sdef in (d.get("services") or {}).items():
                    n = f"{d['domain']}.{sname}"
                    names.add(n)
                    r = (sdef or {}).get("response")
                    if isinstance(r, dict):
                        resp[n] = "optional" if r.get("optional") else "only"
            self._svc = (time.time(), frozenset(names), resp)
        return self._svc[1], self._svc[2]

    async def ws(self, cmd_type, **kw):
        """One short-lived WebSocket per command (no permanent connection, no background task)."""
        async with self.s.ws_connect(self.ws_url, timeout=15, max_msg_size=8 * 1024 * 1024) as ws:
            await ws.receive_json(timeout=10)
            await ws.send_json({"type": "auth", "access_token": self.token})
            if (await ws.receive_json(timeout=10)).get("type") != "auth_ok":
                raise HAError(401, "websocket auth failed")
            await ws.send_json({"id": 1, "type": cmd_type, **kw})
            while True:
                msg = await ws.receive(timeout=20)
                if msg.type != WSMsgType.TEXT:
                    raise HAError(502, "websocket closed")
                d = json.loads(msg.data)
                if d.get("id") == 1:
                    if not d.get("success"):
                        raise HAError(400, str((d.get("error") or {}).get("message", "websocket error")))
                    return d.get("result")

    async def registries(self):
        """areas, devices, entities - fetched on demand, never cached."""
        out = []
        for t in ("area_registry", "device_registry", "entity_registry"):
            try:
                out.append(await self.ws(f"config/{t}/list") or [])
            except Exception:  # noqa: BLE001
                out.append([])
        return out
