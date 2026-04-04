from __future__ import annotations

from fastapi.testclient import TestClient

from substrate.web import app


def test_root_serves_scheduler_studio_ui() -> None:
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Codex Scheduler Studio" in response.text


def test_legacy_panel_and_legacy_api_endpoints_remain_available() -> None:
    with TestClient(app) as client:
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
