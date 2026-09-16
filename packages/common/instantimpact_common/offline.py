"""STRICT_OFFLINE helpers — runtime must not call non-loopback hosts."""

from __future__ import annotations

from urllib.parse import urlparse

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"})


def host_is_loopback(host: str | None) -> bool:
    h = (host or "").strip().lower().strip("[]")
    return h in LOOPBACK_HOSTS


def bind_is_loopback(host: str | None) -> bool:
    """True when the API bind is local-only (not LAN / 0.0.0.0)."""
    h = (host or "").strip().lower()
    if h in {"0.0.0.0", "::", "[::]"}:
        return False
    return host_is_loopback(h)


def url_is_loopback(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return host_is_loopback(parsed.hostname)


def enforce_strict_offline(url: str, enabled: bool) -> None:
    if enabled and not url_is_loopback(url):
        raise RuntimeError(f"STRICT_OFFLINE blocked outbound URL: {url}")
