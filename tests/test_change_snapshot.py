"""Tests for the non-blocking change snapshot engine."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.snapshots import SNAPSHOT_BRANCH, SnapshotEngine, _line_is_suspicious


def test_line_is_suspicious() -> None:
    # Strong tokens always block.
    assert _line_is_suspicious("ghp_1234567890abcdefghijklmnopqrstuvwxyz")
    assert _line_is_suspicious("key = AKIAIOSFODNN7EXAMPLE")
    assert _line_is_suspicious("-----BEGIN RSA PRIVATE KEY-----")
    # Concrete keyword assignments block.
    assert _line_is_suspicious("password = hunter2-secret")
    assert _line_is_suspicious("api_key: 9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c")
    # Placeholders / references / dictionary values / code pass.
    assert not _line_is_suspicious("passwd: files systemd")
    assert not _line_is_suspicious("token: ${{ secrets.GITHUB_TOKEN }}")
    assert not _line_is_suspicious("auth_token: \"${GATEWAY_AUTH_TOKEN}\"")
    assert not _line_is_suspicious("password = <your-password>")
    assert not _line_is_suspicious("password = changeme")
    assert not _line_is_suspicious("token = your_api_token_here")
    assert not _line_is_suspicious("GATEWAY_AUTH_TOKEN=your-secure-token-here")
    assert not _line_is_suspicious("secret = os.environ.get(\"SECRET\")")
    assert not _line_is_suspicious("hosts: files dns myhostname")
    assert not _line_is_suspicious("token = credentials.credentials")
    assert not _line_is_suspicious("api_key = Column(String, unique=True)")
    assert not _line_is_suspicious("api_key=api_key,")
    assert not _line_is_suspicious("app_secret = \"your-app-secret\"")
    assert not _line_is_suspicious("hub.verify_token=your-token&hub.challenge=test123")
    assert not _line_is_suspicious("TOKEN_VALUE=\"${GH_TOKEN:-${GITHUB_TOKEN:-}}\"")
    assert not _line_is_suspicious("GITHUB_TOKEN=ghp_xxxxxxxxxxxx  # optional")
    assert not _line_is_suspicious("export HF_TOKEN=\"hf_****\"")
    assert not _line_is_suspicious("token = candidate")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    return result.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A small git repository with one commit and a handful of files."""
    work = tmp_path / "repo"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.name", "Test")
    git(work, "config", "user.email", "test@example.com")
    (work / "alpha.txt").write_text("alpha\n")
    (work / "beta.txt").write_text("beta\n")
    (work / "tool.sh").write_text("#!/bin/sh\necho hi\n")
    os.chmod(work / "tool.sh", 0o755)
    os.symlink("alpha.txt", work / "link.txt")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "init")
    return work


@pytest.fixture()
def runtime(tmp_path: Path, repo: Path) -> "object":
    """A minimal fake runtime exposing repositories()/resolve_repo()."""
    from types import SimpleNamespace

    cfg = SimpleNamespace(slug="repo", path=repo, allow_mutations=True,
                          default_mode="mutate", tasks={})
    scheduler = SimpleNamespace(default_repo_slug="repo")
    workspace = SimpleNamespace(repositories={"repo": cfg}, scheduler=scheduler,
                                policy=SimpleNamespace())
    return SimpleNamespace(
        workspace=workspace,
        repositories=lambda: {"repo": cfg},
        resolve_repo=lambda slug: cfg,
    )


@pytest.fixture()
def engine(tmp_path: Path, repo: Path) -> SnapshotEngine:
    return SnapshotEngine(tmp_path / "workspace")


def rev_count(repo: Path) -> int:
    try:
        return int(git(repo, "rev-list", "--count", SNAPSHOT_BRANCH))
    except subprocess.CalledProcessError:
        return 0


def snapshot_tree(repo: Path) -> set[str]:
    out = git(repo, "ls-tree", "-r", "--name-only", SNAPSHOT_BRANCH)
    return set(out.splitlines())


def test_first_snapshot_captures_working_tree(engine: SnapshotEngine, repo: Path) -> None:
    result = engine.snapshot_repo("repo", repo)
    assert result["status"] == "success"
    assert result["files_changed"] == 4
    assert result["commit_oid"]
    tree = snapshot_tree(repo)
    assert tree == {"alpha.txt", "beta.txt", "tool.sh", "link.txt"}


def test_snapshot_never_mutates_user_state(engine: SnapshotEngine, repo: Path) -> None:
    head_before = git(repo, "rev-parse", "HEAD")
    status_before = git(repo, "status", "--porcelain")
    result = engine.snapshot_repo("repo", repo)
    assert result["status"] == "success"
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert git(repo, "status", "--porcelain") == status_before
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_incremental_snapshot_captures_only_changes(
    engine: SnapshotEngine, repo: Path
) -> None:
    assert engine.snapshot_repo("repo", repo)["status"] == "success"
    (repo / "alpha.txt").write_text("alpha v2\n")
    (repo / "gamma.txt").write_text("gamma\n")
    os.unlink(repo / "beta.txt")
    result = engine.snapshot_repo("repo", repo)
    assert result["status"] == "success"
    assert result["files_changed"] == 3  # alpha (changed), gamma (added), beta (deleted)
    tree = snapshot_tree(repo)
    assert tree == {"alpha.txt", "gamma.txt", "tool.sh", "link.txt"}
    # snapshot history chains parent -> child
    first = git(repo, "rev-parse", SNAPSHOT_BRANCH)
    second = git(repo, "rev-parse", SNAPSHOT_BRANCH + "~1")
    assert first != second


def test_unchanged_files_are_not_rehashed(
    engine: SnapshotEngine, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert engine.snapshot_repo("repo", repo)["status"] == "success"
    hashed: list[str] = []
    original = engine._hash_object

    def spy(repo_path, rel, abs_path, stat):
        hashed.append(rel)
        return original(repo_path, rel, abs_path, stat)

    monkeypatch.setattr(engine, "_hash_object", spy)
    (repo / "gamma.txt").write_text("gamma\n")
    result = engine.snapshot_repo("repo", repo)
    assert result["status"] == "success"
    assert result["files_changed"] == 1
    assert hashed == ["gamma.txt"]
    tree = snapshot_tree(repo)
    assert tree == {"alpha.txt", "beta.txt", "tool.sh", "link.txt", "gamma.txt"}


def test_modes_and_symlinks_preserved(engine: SnapshotEngine, repo: Path) -> None:
    assert engine.snapshot_repo("repo", repo)["status"] == "success"
    # ls-tree lines: <mode> <type> <oid>\t<path>
    raw = git(repo, "ls-tree", SNAPSHOT_BRANCH)
    modes = {}
    oids = {}
    for line in raw.splitlines():
        fields = line.split("\t")
        meta = fields[0].split()
        modes[fields[1]] = meta[0]
        oids[fields[1]] = meta[2]
    assert modes["tool.sh"] == "100755"
    assert modes["link.txt"] == "120000"
    # symlink blob content is the link target text
    assert git(repo, "cat-file", "-p", oids["link.txt"]) == "alpha.txt"


def test_quiet_no_stdout(engine: SnapshotEngine, repo: Path) -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = engine.snapshot_repo("repo", repo)
    assert result["status"] == "success"
    assert buf.getvalue() == ""


def test_skips_when_index_locked(engine: SnapshotEngine, repo: Path) -> None:
    lock = repo / ".git" / "index.lock"
    lock.write_text("lock")
    try:
        result = engine.snapshot_repo("repo", repo)
        assert result["status"] == "skipped"
        assert "index.lock" in result["error"]
    finally:
        lock.unlink(missing_ok=True)
    assert rev_count(repo) == 0


def test_blocks_on_secret_material(engine: SnapshotEngine, repo: Path) -> None:
    assert engine.snapshot_repo("repo", repo)["status"] == "success"
    (repo / "creds.txt").write_text("api_key = sk-abcdefghijklmnopqrstuvwxyz123456\n")
    result = engine.snapshot_repo("repo", repo)
    assert result["status"] == "blocked"
    assert "secret scan" in result["error"]
    assert rev_count(repo) == 1  # previous snapshot untouched


def test_tracked_secret_like_content_does_not_block(
    engine: SnapshotEngine, repo: Path
) -> None:
    # A tracked file containing secret-looking fixture strings (common in
    # tests/docs/code) is already in git history and must not gate snapshots.
    (repo / "note.txt").write_text("password = hunter2-secret\napi_key: xyz\n")
    git(repo, "add", "note.txt")
    git(repo, "commit", "-q", "-m", "add note")
    result = engine.snapshot_repo("repo", repo)
    assert result["status"] == "success"


def test_binary_files_are_snapshotted(engine: SnapshotEngine, repo: Path) -> None:
    (repo / "blob.bin").write_bytes(bytes(range(256)))
    result = engine.snapshot_repo("repo", repo)
    assert result["status"] == "success"
    assert result["files_changed"] == 5
    assert "blob.bin" in snapshot_tree(repo)


def test_list_and_status(engine: SnapshotEngine, repo: Path, runtime: object) -> None:
    assert engine.snapshot_repo("repo", repo)["status"] == "success"
    commits = engine.list_snapshots(repo, limit=10)
    assert len(commits) == 1
    assert commits[0]["oid"]
    status = engine.status(runtime)
    assert status[0]["repo_slug"] == "repo"
    assert status[0]["commit_oid"] == commits[0]["oid"]
    assert "Substrate Snapshot Bot" in status[0]["author"] or "snapshot@substrate.local" in status[0]["author_email"]


def test_empty_repo_first_snapshot(tmp_path: Path) -> None:
    work = tmp_path / "empty"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.name", "Test")
    git(work, "config", "user.email", "test@example.com")
    (work / "only.txt").write_text("only\n")
    engine = SnapshotEngine(tmp_path / "workspace")
    result = engine.snapshot_repo("empty", work)
    assert result["status"] == "success"
    assert snapshot_tree(work) == {"only.txt"}


def test_nested_directories(engine: SnapshotEngine, repo: Path) -> None:
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hi')\n")
    (repo / "src" / "deep").mkdir()
    (repo / "src" / "deep" / "util.py").write_text("def f():\n    pass\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text("# Guide\n")
    result = engine.snapshot_repo("repo", repo)
    assert result["status"] == "success"
    tree = snapshot_tree(repo)
    assert tree == {
        "alpha.txt", "beta.txt", "tool.sh", "link.txt",
        "src/main.py", "src/deep/util.py", "docs/guide.md",
    }
    # tree object at src is a real subtree with mode 040000
    raw = git(repo, "ls-tree", SNAPSHOT_BRANCH)
    src_line = [ln for ln in raw.splitlines() if ln.endswith("\tsrc")][0]
    assert src_line.startswith("040000 tree")
    # verify content via archive
    import tarfile
    archive = subprocess.run(
        ["git", "archive", SNAPSHOT_BRANCH],
        cwd=repo, capture_output=True, check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
        names = set(tf.getnames())
    assert "src/deep/util.py" in names
