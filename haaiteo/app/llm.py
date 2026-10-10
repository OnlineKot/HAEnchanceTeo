"""Anthropic Messages + Gemini generateContent clients (aiohttp only, no SDKs) behind one neutral interface.
History is neutral: {"r":"user","text"} | {"r":"assistant","text","calls":[{id,name,args,sig?}]} | {"r":"tool","results":[{id,name,content,error?}]}
By TeodorTeo.com (https://teodorteo.com)."""
import json

from aiohttp import ClientTimeout

from ha import read_limited, HAError

ANTHROPIC_URL_DEFAULT = "https://api.anthropic.com"
GEMINI_URL_DEFAULT = "https://generativelanguage.googleapis.com"
MAX_TOKENS = 4096


class LLMError(Exception):
    pass


def _merge(msgs, role, parts, key):
    if msgs and msgs[-1]["role"] == role:
        msgs[-1][key].extend(parts)
    else:
        msgs.append({"role": role, key: list(parts)})


def to_anthropic(history):
    msgs = []
    for s in history:
        if s["r"] == "user":
            _merge(msgs, "user", [{"type": "text", "text": s["text"] or "."}], "content")
        elif s["r"] == "assistant":
            blocks = []
            if s.get("text"):
                blocks.append({"type": "text", "text": s["text"]})
            for c in s.get("calls") or []:
                blocks.append({"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"] if isinstance(c["args"], dict) else {}})
            _merge(msgs, "assistant", blocks or [{"type": "text", "text": "(no output)"}], "content")
        else:
            _merge(msgs, "user", [{"type": "tool_result", "tool_use_id": r["id"], "content": r["content"] or "(empty)",
                                   **({"is_error": True} if r.get("error") else {})} for r in s["results"]], "content")
    return msgs


def to_gemini(history):
    msgs = []
    for s in history:
        if s["r"] == "user":
            _merge(msgs, "user", [{"text": s["text"] or "."}], "parts")
        elif s["r"] == "assistant":
            parts = [{"text": s["text"]}] if s.get("text") else []
            for c in s.get("calls") or []:
                p = {"functionCall": {"name": c["name"], "args": c["args"] if isinstance(c["args"], dict) else {}}}
                if c.get("sig"):
                    p["thoughtSignature"] = c["sig"]
                parts.append(p)
            _merge(msgs, "model", parts or [{"text": "(no output)"}], "parts")
        else:
            _merge(msgs, "user", [{"functionResponse": {"name": r["name"], "response": {"output": r["content"] or "(empty)", **({"error": True} if r.get("error") else {})}}}
                                  for r in s["results"]], "parts")
    return msgs


def gem_schema(s):
    t = s.get("type", "string")
    d = s.get("description")
    if t == "object":
        props = s.get("properties")
        if not props:  # Gemini rejects free-form objects -> JSON string, parsed back by the tool layer
            return {"type": "STRING", "description": ((d or "") + " (JSON-encoded object)").strip()}
        o = {"type": "OBJECT", "properties": {k: gem_schema(v) for k, v in props.items()}}
        if s.get("required"):
            o["required"] = s["required"]
    elif t == "array":
        o = {"type": "ARRAY", "items": gem_schema(s.get("items") or {"type": "string"})}
    else:
        o = {"type": {"integer": "INTEGER", "number": "NUMBER", "boolean": "BOOLEAN"}.get(t, "STRING")}
        if s.get("enum"):
            o["enum"] = s["enum"]
    if d and "description" not in o:
        o["description"] = d
    return o


async def _post(session, url, headers, body, secrets, timeout=120):
    try:
        async with session.post(url, json=body, headers=headers, timeout=ClientTimeout(total=timeout, connect=15)) as r:
            raw = await read_limited(r, 4 * 1024 * 1024)
            status = r.status
    except HAError:
        raise LLMError("response too large")
    except Exception as exc:  # noqa: BLE001
        raise LLMError(scrub(f"request failed: {type(exc).__name__} {exc}", secrets))
    try:
        data = json.loads(raw)
    except ValueError:
        raise LLMError(f"invalid (non-JSON) response from the API, HTTP {status}")
    if status >= 400 or not isinstance(data, dict):
        e = data.get("error") if isinstance(data, dict) else None
        msg = e.get("message") if isinstance(e, dict) else (e or str(data)[:200])
        raise LLMError(scrub(f"API error {status}: {msg}", secrets)[:400])
    return data


def scrub(text, secrets):
    for k in secrets:
        if k:
            text = text.replace(k, "***")
    return text


async def complete_anthropic(session, base, key, model, system, history, tools):
    body = {"model": model, "max_tokens": MAX_TOKENS, "system": system, "messages": to_anthropic(history)}
    if tools:
        body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
    d = await _post(session, base.rstrip("/") + "/v1/messages",
                    {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, body, [key])
    text, calls = [], []
    for b in d.get("content") or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            text.append(str(b.get("text", "")))
        elif b.get("type") == "tool_use":
            args = b.get("input")
            calls.append({"id": str(b.get("id") or f"tu{len(calls)}"), "name": str(b.get("name", "")), "args": args if isinstance(args, dict) else {"_invalid": str(args)[:200]}})
    u = d.get("usage") or {}
    return {"text": "".join(text).strip(), "calls": calls, "in": int(u.get("input_tokens") or 0), "out": int(u.get("output_tokens") or 0),
            "stop": d.get("stop_reason")}


async def complete_gemini(session, base, key, model, system, history, tools):
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": to_gemini(history),
            "generationConfig": {"maxOutputTokens": MAX_TOKENS}}
    if tools:
        decl = []
        for t in tools:
            x = {"name": t["name"], "description": t["description"]}
            if t["parameters"].get("properties"):
                x["parameters"] = gem_schema(t["parameters"])
            decl.append(x)
        body["tools"] = [{"functionDeclarations": decl}]
    d = await _post(session, f"{base.rstrip('/')}/v1beta/models/{model}:generateContent",
                    {"x-goog-api-key": key, "content-type": "application/json"}, body, [key])
    cands = d.get("candidates") or []
    if not cands:
        fb = (d.get("promptFeedback") or {}).get("blockReason")
        raise LLMError(f"Gemini returned no answer{' (blocked: ' + str(fb) + ')' if fb else ''}")
    c = cands[0] if isinstance(cands[0], dict) else {}
    text, calls = [], []
    for p in (c.get("content") or {}).get("parts") or []:
        if not isinstance(p, dict):
            continue
        if isinstance(p.get("functionCall"), dict):
            fc = p["functionCall"]
            args = fc.get("args", {})
            calls.append({"id": f"g{len(calls)}_{abs(hash(str(fc))) % 100000}", "name": str(fc.get("name", "")),
                          "args": args if isinstance(args, dict) else {"_invalid": str(args)[:200]}, "sig": p.get("thoughtSignature")})
        elif p.get("text") and not p.get("thought"):
            text.append(str(p["text"]))
    u = d.get("usageMetadata") or {}
    return {"text": "".join(text).strip(), "calls": calls, "in": int(u.get("promptTokenCount") or 0),
            "out": int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0), "stop": c.get("finishReason")}
