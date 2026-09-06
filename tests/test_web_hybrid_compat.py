from __future__ import annotations

from fastapi.testclient import TestClient

from substrate import web
from substrate.web import (
    _RATE_LIMITS,
    _TAILNET_HOSTS_CACHE,
    app,
)

# State-changing requests now enforce a loopback/tailnet Host allowlist, so the
# test client must present a valid loopback Host header (the default is
# "testserver").
CLIENT_KWARGS = {"base_url": "http://127.0.0.1:8090"}


def test_root_redirects_to_control_panel() -> None:
    with TestClient(app, follow_redirects=False, **CLIENT_KWARGS) as client:
        response = client.get("/")
        assert response.status_code == 302
        assert "/panel" in response.headers["location"]

        panel = client.get("/panel")
        assert panel.status_code == 200
        assert "Substrate Control Panel" in panel.text


def test_legacy_panel_and_legacy_api_endpoints_remain_available() -> None:
    with TestClient(app, **CLIENT_KWARGS) as client:
        legacy = client.get("/legacy")
        assert legacy.status_code == 200
        assert "Substrate Ops Panel" in legacy.text

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        payload = dashboard.json()
        assert "metrics" in payload
        assert "stage_sequence" in payload
        assert "pass_sequence" in payload

        scan = client.post("/api/actions/scan")
        assert scan.status_code == 200
        scan_body = scan.json()
        assert scan_body["ok"] is True
        assert isinstance(scan_body["count"], int)


def test_state_changing_requests_reject_unknown_host() -> None:
    # The default TestClient Host header ("testserver") is not on the panel
    # allowlist; state-changing requests must use a loopback/tailnet host.
    with TestClient(app, follow_redirects=False) as client:
        resp = client.post("/api/actions/scan", headers={"Host": "testserver"})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "host_forbidden"


def test_cross_origin_state_changing_requests_rejected() -> None:
    with TestClient(app, **CLIENT_KWARGS) as client:
        resp = client.post(
            "/api/actions/scan",
            headers={"Origin": "http://evil.example"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "origin_forbidden"


def test_tailnet_https_origin_allowed(monkeypatch) -> None:
    # Force a tailnet host-list refresh so the TAILSCALE_HOST override applies.
    # Resetting only the timestamp was unreliable: on a fresh runner
    # time.monotonic() starts near 0, so `now - 0.0 < TTL` treated the cached
    # (empty) host set as fresh and the override was ignored, returning 403.
    # Reset to the "never computed" sentinel (-inf) so a recompute is forced
    # regardless of clock offset.
    _TAILNET_HOSTS_CACHE["at"] = float("-inf")
    _TAILNET_HOSTS_CACHE["hosts"] = set()
    monkeypatch.setenv("TAILSCALE_HOST", "myhost.tail1234.ts.net")
    with TestClient(app, **CLIENT_KWARGS) as client:
        resp = client.post(
            "/api/actions/scan",
            headers={"Origin": "https://myhost.tail1234.ts.net:10000"},
        )
        assert resp.status_code == 200


def test_bearer_token_required_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("PANEL_AUTH_TOKEN", "test-token-123")
    with TestClient(app, **CLIENT_KWARGS) as client:
        denied = client.post("/api/actions/scan")
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "unauthorized"

        allowed = client.post(
            "/api/actions/scan",
            headers={"Authorization": "Bearer test-token-123"},
        )
        assert allowed.status_code == 200


def test_auth_bootstrap_exposes_no_token_when_unconfigured() -> None:
    with TestClient(app, **CLIENT_KWARGS) as client:
        resp = client.get("/__panel_auth_bootstrap__.js")
        assert resp.status_code == 200
        assert "window.PANEL_AUTH_TOKEN" in resp.text


def test_rate_limiting_returns_429_with_retry_after() -> None:
    original = web.RATE_LIMIT_MAX_REQUESTS
    web.RATE_LIMIT_MAX_REQUESTS = 5
    try:
        with TestClient(app, **CLIENT_KWARGS) as client:
            responses = [client.get("/api/dashboard") for _ in range(8)]
        limited = [r for r in responses if r.status_code == 429]
        assert limited, "expected at least one 429 after exceeding the limit"
        assert "Retry-After" in limited[0].headers
    finally:
        web.RATE_LIMIT_MAX_REQUESTS = original
        _RATE_LIMITS.clear()
