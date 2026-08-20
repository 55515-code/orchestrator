"""API tests for the secure vault (keyring-backed secrets).

These exercise the vault endpoints through the encrypted-file fallback so
the tests run headless without a SecretService/keyring daemon. The security
invariants checked:

- Raw secrets never appear in GET responses (only masked previews).
- The integrations-state file stores only an opaque pointer, never the value.
- PUT validates unknown services and oversized secrets.
- DELETE disconnects and removes the stored value.

All state (encrypted file + integrations-state.json) is isolated under
tmp_path — nothing touches the real workspace keyring or state files.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from substrate import vault
from substrate.registry import SubstrateRuntime
from substrate.web import app

CLIENT_KWARGS = {"base_url": "http://127.0.0.1:8090"}


def _make_runtime(tmp_path: Path) -> SubstrateRuntime:
    """A runtime rooted at tmp_path with a real integration catalog."""
    root = tmp_path / "workspace"
    (root / "state").mkdir(parents=True, exist_ok=True)
    # Copy the real integration catalog so service ids are available.
    repo_integrations = Path(__file__).resolve().parents[1] / "integrations.yaml"
    if repo_integrations.exists():
        shutil.copy(repo_integrations, root / "integrations.yaml")
    return SubstrateRuntime(root=root)


def _install_file_backend(monkeypatch, runtime: SubstrateRuntime):
    """Point the vault module at a CredentialStore that uses the encrypted
    file fallback rooted at the tmp runtime (no keyring daemon needed)."""
    store = vault.CredentialStore(runtime.root)
    store._keyring_available = False
    monkeypatch.setattr(vault, "CredentialStore", lambda root: store)
    return store


def _use_runtime(monkeypatch, runtime: SubstrateRuntime):
    """Make both the vault and web modules use the tmp runtime."""
    monkeypatch.setattr(vault, "RUNTIME", runtime, raising=False)
    import substrate.web as web_mod

    monkeypatch.setattr(web_mod, "RUNTIME", runtime)


def test_vault_status_reports_services_without_secrets(monkeypatch, tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    _install_file_backend(monkeypatch, runtime)
    _use_runtime(monkeypatch, runtime)

    payload = vault.vault_status(runtime)
    summary = payload["summary"]
    assert summary["services_total"] >= 1
    assert summary["secured_total"] == 0
    assert summary["missing_total"] == summary["services_total"]
    for svc in payload["services"]:
        assert svc["has_secret"] is False
        assert svc["preview"] in ("—", None)


def test_vault_put_and_delete_roundtrip_via_api(monkeypatch, tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    store = _install_file_backend(monkeypatch, runtime)
    _use_runtime(monkeypatch, runtime)
    assert store._keyring_available is False

    secret = "FAKE_TEST_TOKEN_abcdefghij_9876543210"

    with TestClient(app, **CLIENT_KWARGS) as client:
        status = client.get("/api/vault/status")
        assert status.status_code == 200
        ids = [s["id"] for s in status.json()["services"]]
        assert "github" in ids, f"github missing from catalog: {ids[:5]}"

        put = client.post(
            "/api/vault/put",
            data={
                "service_id": "github",
                "secret": secret,
                "auth_method": "personal_access_token",
                "access_mode": "read",
            },
        )
        assert put.status_code == 200, put.text
        body = put.json()
        assert body["ok"] is True
        assert body["pointer"] == "keyring:integration:github"

        # State file has the pointer, never the value.
        state_text = (runtime.paths["integrations_state"]).read_text(encoding="utf-8")
        assert "keyring:integration:github" in state_text
        assert secret not in state_text

        # Encrypted file exists (fallback backend) and contains the key but
        # the value is Fernet-encrypted, not plaintext.
        enc_file = runtime.root / "state" / "credentials.enc"
        assert enc_file.exists()
        enc_bytes = enc_file.read_bytes()
        assert secret.encode() not in enc_bytes

        # Status now shows secured with a masked preview only.
        status2 = client.get("/api/vault/status")
        assert status2.status_code == 200
        svc = next(s for s in status2.json()["services"] if s["id"] == "github")
        assert svc["has_secret"] is True
        assert svc["preview"] != secret
        assert "FAKE_TEST_TOKEN_abc" not in (svc["preview"] or "")

        # DELETE removes it and disconnects.
        delete = client.post("/api/vault/delete", data={"service_id": "github"})
        assert delete.status_code == 200
        assert delete.json()["removed"] is True
        status3 = client.get("/api/vault/status")
        svc3 = next(s for s in status3.json()["services"] if s["id"] == "github")
        assert svc3["has_secret"] is False
        assert svc3["connected"] is False


def test_vault_put_rejects_unknown_service(monkeypatch, tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    _install_file_backend(monkeypatch, runtime)
    _use_runtime(monkeypatch, runtime)
    with TestClient(app, **CLIENT_KWARGS) as client:
        resp = client.post(
            "/api/vault/put",
            data={"service_id": "not_a_service", "secret": "whatever"},
        )
        assert resp.status_code == 404


def test_vault_put_rejects_oversized_secret(monkeypatch, tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    _install_file_backend(monkeypatch, runtime)
    _use_runtime(monkeypatch, runtime)
    with TestClient(app, **CLIENT_KWARGS) as client:
        resp = client.post(
            "/api/vault/put",
            data={"service_id": "github", "secret": "x" * 9000},
        )
        assert resp.status_code == 400


def test_vault_put_requires_secret(monkeypatch, tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    _install_file_backend(monkeypatch, runtime)
    _use_runtime(monkeypatch, runtime)
    with TestClient(app, **CLIENT_KWARGS) as client:
        # Whitespace-only secret fails the vault layer's own validation (400).
        resp = client.post(
            "/api/vault/put",
            data={"service_id": "github", "secret": "   "},
        )
        assert resp.status_code == 400


def test_vault_status_never_exposes_secret_values(monkeypatch, tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    _install_file_backend(monkeypatch, runtime)
    _use_runtime(monkeypatch, runtime)

    secret = "super-secret-value-987654321"
    with TestClient(app, **CLIENT_KWARGS) as client:
        client.post(
            "/api/vault/put",
            data={"service_id": "slack", "secret": secret},
        )
        status = client.get("/api/vault/status")
        assert status.status_code == 200
        payload = status.json()
        assert secret not in str(payload)
        for svc in payload["services"]:
            assert "secret" not in svc or svc.get("preview") != secret
            assert "token" not in svc or svc.get("token_ref") != secret
