"""Security tests: the rate limiter must not trust spoofable forwarding headers.

Regression coverage for a spoofable rate-limit bypass. A remote client could
previously (a) send ``X-Forwarded-For: 127.0.0.1`` to be treated as a *local*
request and (b) rotate ``X-Forwarded-For`` values to dodge per-IP limiting,
because the limiter honoured the forwarding headers unconditionally.

Forwarding headers (``X-Forwarded-For`` / ``X-Real-IP``) must only be honoured
when the immediate peer (``request.client.host``) is a trusted proxy. The set
of trusted proxies is configured via the ``TRUSTED_PROXY_IPS`` env var and
always includes loopback (the only legitimate proxy in this single-tenant
local-research deployment). Otherwise both ``is_local_request`` and
``get_client_identity`` fall back to the real peer address.
"""

import pytest
from starlette.requests import Request

from src.middleware.rate_limiter import RateLimiter

# TEST-NET-3 (RFC 5737) — stands in for an attacker out on the public internet.
PUBLIC_PEER = "203.0.113.5"
# A proxy the operator explicitly trusts via TRUSTED_PROXY_IPS.
TRUSTED_PROXY = "10.0.0.5"


def build_request(path="/api/v1/data", headers=None, client=(PUBLIC_PEER, 44321)):
    """Construct a minimal Starlette ``Request`` from an ASGI scope.

    ``client`` is the (host, port) of the immediate peer, or ``None`` to model a
    request with no client information.
    """
    raw_headers = [
        (str(name).lower().encode("latin-1"), str(value).encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("latin-1"),
        "query_string": b"",
        "root_path": "",
        "headers": raw_headers,
        "client": tuple(client) if client else None,
        "server": ("testserver", 80),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _clear_trusted_proxy_env(monkeypatch):
    """Default-path tests must not pick up an operator's ambient allowlist."""
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)


# --------------------------------------------------------------------------
# Spoofed forwarding headers from an untrusted peer must be ignored.
# --------------------------------------------------------------------------


def test_spoofed_forwarded_for_loopback_is_not_local_from_untrusted_peer():
    limiter = RateLimiter()
    request = build_request(
        headers={"X-Forwarded-For": "127.0.0.1"}, client=(PUBLIC_PEER, 5000)
    )
    assert limiter.is_local_request(request) is False


def test_spoofed_real_ip_loopback_is_not_local_from_untrusted_peer():
    limiter = RateLimiter()
    request = build_request(
        headers={"X-Real-IP": "127.0.0.1"}, client=(PUBLIC_PEER, 5000)
    )
    assert limiter.is_local_request(request) is False


def test_identity_ignores_forwarded_for_from_untrusted_peer():
    limiter = RateLimiter()
    request = build_request(
        headers={"X-Forwarded-For": "198.51.100.7"}, client=(PUBLIC_PEER, 5000)
    )
    identity = limiter.get_client_identity(request)
    assert identity["identity_type"] == "ip"
    assert identity["subject"] == f"ip:{PUBLIC_PEER}"


def test_rotating_forwarded_for_cannot_escape_per_ip_limit():
    """The core attack: rotate XFF to dodge per-IP limiting.

    All rotated requests must collapse onto the single real-peer identity, so
    only ``burst_size`` requests are allowed and the rest are blocked.
    """
    limiter = RateLimiter(requests_per_minute=2, burst_size=2)
    results = []
    subjects = set()
    for index in range(6):
        request = build_request(
            headers={"X-Forwarded-For": f"198.51.100.{index}"},
            client=(PUBLIC_PEER, 5000 + index),
        )
        outcome = limiter.evaluate(request)
        results.append(outcome["allowed"])
        subjects.add(outcome["subject"])

    assert subjects == {f"ip:{PUBLIC_PEER}"}
    assert results == [True, True, False, False, False, False]


def test_loopback_proxy_must_not_launder_remote_client_into_local():
    """A local reverse proxy (loopback peer) forwarding a remote client must
    surface the *remote* client — not be treated as a local request."""
    limiter = RateLimiter()
    request = build_request(
        headers={"X-Forwarded-For": "8.8.8.8"}, client=("127.0.0.1", 5000)
    )
    assert limiter.is_local_request(request) is False
    assert limiter.get_client_identity(request)["subject"] == "ip:8.8.8.8"


# --------------------------------------------------------------------------
# Genuine localhost posture is preserved.
# --------------------------------------------------------------------------


def test_genuine_loopback_peer_is_treated_as_local():
    limiter = RateLimiter()
    request = build_request(headers={}, client=("127.0.0.1", 5000))
    assert limiter.is_local_request(request) is True


def test_genuine_ipv6_loopback_peer_is_treated_as_local():
    limiter = RateLimiter()
    request = build_request(headers={}, client=("::1", 5000))
    assert limiter.is_local_request(request) is True


def test_loopback_peer_identity_is_peer_based_without_headers():
    limiter = RateLimiter()
    request = build_request(headers={}, client=("127.0.0.1", 5000))
    assert limiter.get_client_identity(request)["subject"] == "ip:127.0.0.1"


# --------------------------------------------------------------------------
# A configured trusted proxy IS honoured.
# --------------------------------------------------------------------------


def test_trusted_proxy_via_env_uses_forwarded_client_ip(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", TRUSTED_PROXY)
    limiter = RateLimiter()
    request = build_request(
        headers={"X-Forwarded-For": "198.51.100.7"}, client=(TRUSTED_PROXY, 5000)
    )
    identity = limiter.get_client_identity(request)
    assert identity["identity_type"] == "ip"
    assert identity["subject"] == "ip:198.51.100.7"


def test_trusted_proxy_via_env_uses_real_ip_header(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", TRUSTED_PROXY)
    limiter = RateLimiter()
    request = build_request(
        headers={"X-Real-IP": "198.51.100.7"}, client=(TRUSTED_PROXY, 5000)
    )
    assert limiter.get_client_identity(request)["subject"] == "ip:198.51.100.7"


def test_trusted_proxy_forwarding_loopback_client_is_local(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", TRUSTED_PROXY)
    limiter = RateLimiter()
    request = build_request(
        headers={"X-Forwarded-For": "127.0.0.1"}, client=(TRUSTED_PROXY, 5000)
    )
    assert limiter.is_local_request(request) is True


def test_multiple_trusted_proxies_parsed_from_env(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.5, 192.168.1.10")
    limiter = RateLimiter()
    request = build_request(
        headers={"X-Forwarded-For": "198.51.100.7"}, client=("192.168.1.10", 5000)
    )
    assert limiter.get_client_identity(request)["subject"] == "ip:198.51.100.7"


def test_untrusted_peer_ignores_forwarded_even_when_other_proxy_trusted(monkeypatch):
    """Configuring one trusted proxy must not make *every* peer trusted."""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", TRUSTED_PROXY)
    limiter = RateLimiter()
    request = build_request(
        headers={"X-Forwarded-For": "198.51.100.7"}, client=(PUBLIC_PEER, 5000)
    )
    assert limiter.get_client_identity(request)["subject"] == f"ip:{PUBLIC_PEER}"


# --------------------------------------------------------------------------
# Higher-precedence identities (auth/api-key) are unaffected by the change.
# --------------------------------------------------------------------------


def test_authorization_identity_takes_precedence_over_peer():
    limiter = RateLimiter()
    request = build_request(
        headers={"Authorization": "Bearer abc.def.ghi", "X-Forwarded-For": "127.0.0.1"},
        client=(PUBLIC_PEER, 5000),
    )
    assert limiter.get_client_identity(request)["identity_type"] == "bearer"
