from __future__ import annotations

from fastapi.testclient import TestClient

from substrate.web import app


def test_healthz_reports_gateway_readiness_details() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "local-agent-substrate-ops-panel"
    assert "checks" in payload
    assert payload["checks"]["runtime"]["status"] in {"ok", "degraded"}
    assert payload["checks"]["scheduler"]["status"] in {"ok", "degraded"}
    assert payload["checks"]["openclaw"]["status"] in {"available", "unavailable"}
    assert "reason" in payload["checks"]["openclaw"]
    assert payload["checks"]["providers"]["local"]["status"] in {
        "available",
        "temporarily_unavailable",
    }
    assert payload["checks"]["providers"]["gcloud"]["status"] in {
        "available",
        "temporarily_unavailable",
    }
