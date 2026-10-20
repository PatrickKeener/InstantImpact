"""Optional Ollama rewrite of template ad copy. Idle-time only — GPU jobs pause Ollama."""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("instantimpact.captions")


async def rewrite_ad_copy(
    template: dict[str, Any],
    *,
    url: str,
    model: str,
) -> dict[str, Any] | None:
    """Return primary/short/cta (and variants if present) rewritten by Ollama.

    Connection failures return None so callers keep the template.
    """
    prompt = (
        "Rewrite these marketing captions in the same voice. Keep them short. "
        "The subject is a clearly adult synthetic persona, not a real person. "
        "Return JSON only with keys primary, short, cta, and optional variants "
        "(list of objects with caption, short, cta, hook).\n\n"
        f"character: {template.get('character_name') or ''}\n"
        f"tone: {template.get('tone') or ''}\n"
        f"cta_style: {template.get('cta_style') or ''}\n"
        f"product: {template.get('product_name') or ''}\n"
        f"primary: {template.get('primary') or ''}\n"
        f"short: {template.get('short') or ''}\n"
        f"cta: {template.get('cta') or ''}\n"
    )
    payload = {
        "model": (model or "llama3.1").strip(),
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    endpoint = (url or "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=2.0)) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        log.info("Ollama caption rewrite skipped: %s", exc)
        return None

    raw = body.get("response") if isinstance(body, dict) else None
    parsed = _parse_json_object(raw)
    if not parsed:
        return None
    primary = str(parsed.get("primary") or "").strip()
    short = str(parsed.get("short") or "").strip()
    cta = str(parsed.get("cta") or "").strip()
    if not primary:
        return None
    out: dict[str, Any] = {
        "primary": primary,
        "short": short or primary[:140],
        "cta": cta or str(template.get("cta") or ""),
    }
    variants = parsed.get("variants")
    if isinstance(variants, list) and variants:
        cleaned = []
        for row in variants:
            if not isinstance(row, dict):
                continue
            caption = str(row.get("caption") or "").strip()
            if not caption:
                continue
            cleaned.append(
                {
                    "caption": caption,
                    "short": str(row.get("short") or caption[:140]).strip(),
                    "cta": str(row.get("cta") or out["cta"]).strip(),
                    "hook": str(row.get("hook") or "").strip(),
                }
            )
        if cleaned:
            out["variants"] = cleaned
    return out


def _parse_json_object(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None
