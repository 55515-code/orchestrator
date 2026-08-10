"""Non-blocking working-tree change snapshot engine.

Captures point-in-time snapshots of repository working trees onto a local
``autosnap`` branch using git plumbing only (``hash-object``/``mktree``/
``commit-tree``/``update-ref``).

Guarantees
----------
- **Non-blocking:** never touches the user's index, HEAD, current branch,
  stash, or working tree. No ``git add``/``reset``/``checkout``/``stash``/
  ``merge``/``rebase``/``push`` is ever issued. The engine only writes loose
  objects and one ref (``refs/heads/autosnap``), so it cannot disrupt
  in-progress work or cause users to wait.
- **Quiet:** no diff output is ever produced. Change detection uses stat
  fingerprints plus ``git ls-files``; the engine emits nothing to stdout and
  returns data structures. The CLI prints one compact JSON result per repo.
- **Fast:** unchanged files are skipped via a stat-based manifest (no hashing
  needed). Only changed/added files are hashed, in a single batched
  ``hash-object`` call per repo.
- **Safe:** skips a repo when ``.git/index.lock`` exists, when a git process
  is active on it, or when another snapshot is already running (flock).
  Only newly added *untracked* files are scanned for secret-like material
  (same intent as ``scripts/scan_secrets.sh``); tracked files are already in
  the repository history, so they do not gate snapshots. On a hit the
  snapshot is refused.
- **Local:** snapshots are never pushed anywhere.

Restoring a snapshot (manual, documented in docs/change-snapshots.md):

    git -C <repo> archive autosnap | tar -x -C <target>
    # or selective:
    git -C <repo> checkout autosnap -- <paths>
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat as stat_module
import subprocess
import time
from pathlib import Path
from typing import Any

SNAPSHOT_BRANCH = "autosnap"
# Unambiguous credential material: real API tokens and private keys. Anything
# matching blocks the snapshot (mirrors scripts/scan_secrets.sh).
STRONG_TOKEN = re.compile(
    r"ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|"
    r"hf_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE,
)
# Secret-like keyword assignments, e.g. `password = ...`, `api_key: ...`.
# Used with value-level checks: placeholder, masked, environment, and code
# references are benign; concrete values are suspicious. The leading word
# boundary keeps composite names like GITHUB_TOKEN / access_token / ${VAR:-}
# out of the heuristic (those are references, not assignments).
KEY_ASSIGN = re.compile(
    r"\b(?:password|passwd|api[_-]?key|client_secret|secret|token)\s*[:=]\s*(\S+)",
    re.IGNORECASE,
)
# Masked/redacted values, e.g. hf_**** or ghp_xxx or sk-#####
MASKED_VALUE = re.compile(r"^[\w./:-]*[*xX#]{2,}$")
BENIGN_VALUES = {
    "none", "nil", "true", "false", "example", "changeme", "placeholder",
    "files", "systemd", "ldap", "nis", "db", "compat", "sss",
}
GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0"}
GIT_TIMEOUT = 60


def _line_is_suspicious(line: str) -> bool:
    """True when a line carries credential material worth blocking on.

    Matches the intent of scripts/scan_secrets.sh (which inspects added diff
    lines) without staging anything: strong tokens are always blocked, while
    keyword assignments only block when the value looks like a real
    credential rather than a placeholder, masked value, environment
    reference, or code expression.
    """
    if STRONG_TOKEN.search(line):
        return True
    match = KEY_ASSIGN.search(line)
    if not match:
        return False
    value = match.group(1).strip("\"'")
    lowered = value.lower().rstrip(",;")
    if value.startswith("${") or value.startswith("${{") or value.startswith("$("):
        return False  # ${VAR} / ${{ expr }} / $(cmd) reference
    if value.startswith("<") and value.endswith(">"):
        return False  # <password> style placeholder
    if lowered in BENIGN_VALUES or lowered.startswith("your_") or lowered.startswith("your-"):
        return False  # dictionary word / your_token style placeholder
    if (
        lowered.startswith("os.environ")
        or lowered.startswith("os.getenv")
        or lowered.startswith("process.env")
        or lowered.startswith("environ")
    ):
        return False  # reading from the environment, not embedding a secret
    if MASKED_VALUE.match(value):
        return False  # redacted, e.g. hf_**** or ghp_xxx
    if "." in lowered or "(" in lowered:
        return False  # attribute access / function call, e.g. credentials.credentials
    key_name = match.group(0).split("=", 1)[0].split(":", 1)[0].strip().lower()
    if lowered == key_name:
        return False  # self-reference, e.g. api_key=api_key
    if len(value) < 6:
        return False
    has_special = any(not c.isalnum() for c in value) or any(c.isdigit() for c in value)
    return has_special or len(value) >= 12


class SnapshotEngine:
    """Capture non-blocking working-tree snapshots for one or more repos."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.state_dir = self.root / "state" / "change-snapshots"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ public

    def snapshot_all(self, runtime: Any) -> list[dict[str, Any]]:
        """Snapshot the explicit workspace repositories. Never raises.

        Only explicit workspace.yaml repositories are included in the default
        cycle. Auto-discovered repositories (upstream mirrors, deep deps) can
        be enormous and are excluded to keep the cycle fast and quiet; target
        one explicitly with ``--repo``. When two slugs resolve to the same
        working tree (e.g. ``substrate-core`` and a stub at the root), the
        workspace ``default_repo_slug`` wins.
        """
        explicit = set(runtime.workspace.repositories.keys())
        default = getattr(runtime.workspace.scheduler, "default_repo_slug", None)
        slugs: list[str] = []
        if default in explicit:
            slugs.append(default)
        slugs += sorted(explicit - {default})

        results: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for slug in slugs:
            repo = runtime.resolve_repo(slug)
            repo_path = (self.root / repo.path).resolve()
            if str(repo_path) in seen_paths:
                results.append(
                    {
                        "repo_slug": slug,
                        "repo_path": str(repo_path),
                        "status": "skipped",
                        "commit_oid": None,
                        "files_changed": 0,
                        "duration_ms": 0,
                        "error": "duplicate repository path (already snapshotted)",
                    }
                )
                continue
            seen_paths.add(str(repo_path))
            results.append(self.snapshot_repo(slug, repo_path))
        return results

    def snapshot_repo(self, slug: str, repo_path: Path) -> dict[str, Any]:
        """Capture one snapshot for a repo. Non-blocking: skips when busy."""
        start = time.monotonic()

        def result(status: str, **extra: Any) -> dict[str, Any]:
            return {
                "repo_slug": slug,
                "repo_path": str(repo_path),
                "status": status,
                "commit_oid": None,
                "files_changed": 0,
                "duration_ms": int((time.monotonic() - start) * 1000),
                **extra,
            }

        if not (repo_path / ".git").exists() and not (repo_path / ".git").is_file():
            return result("skipped", error="not a git repository")

        lock_path = self.state_dir / f"{slug}.lock"
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            return result("skipped", error=f"cannot open lock: {exc}")
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return result("skipped", error="another snapshot is running")

            if (repo_path / ".git" / "index.lock").exists():
                return result("skipped", error="index.lock present")
            if self._git_busy(repo_path):
                return result("skipped", error="git process active on repo")

            try:
                return self._capture(slug, repo_path, start)
            except subprocess.SubprocessError as exc:
                return result("error", error=f"git subprocess failed: {exc}")
            except OSError as exc:
                return result("error", error=str(exc))
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_fd)

    def status(self, runtime: Any) -> list[dict[str, Any]]:
        """Report the most recent snapshot commit for each repository."""
        explicit = set(runtime.workspace.repositories.keys())
        default = getattr(runtime.workspace.scheduler, "default_repo_slug", None)
        slugs: list[str] = []
        if default in explicit:
            slugs.append(default)
        slugs += sorted(explicit - {default})
        out: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for slug in slugs:
            repo = runtime.resolve_repo(slug)
            repo_path = (self.root / repo.path).resolve()
            if str(repo_path) in seen_paths:
                continue
            seen_paths.add(str(repo_path))
            oid = self._rev_parse(repo_path, f"refs/heads/{SNAPSHOT_BRANCH}")
            if not oid:
                out.append(
                    {
                        "repo_slug": slug,
                        "repo_path": str(repo_path),
                        "commit_oid": None,
                        "error": "no snapshots yet",
                    }
                )
                continue
            lines = self._git(
                repo_path,
                ["log", "-1", "--format=%an%n%ae%n%aI%n%s", oid],
            ).splitlines()
            out.append(
                {
                    "repo_slug": slug,
                    "repo_path": str(repo_path),
                    "commit_oid": oid,
                    "author": lines[0] if len(lines) > 0 else "",
                    "author_email": lines[1] if len(lines) > 1 else "",
                    "date": lines[2] if len(lines) > 2 else "",
                    "subject": lines[3] if len(lines) > 3 else "",
                }
            )
        return out

    def list_snapshots(self, repo_path: Path, limit: int = 20) -> list[dict[str, Any]]:
        """List snapshot commits for a repo, newest first."""
        ref = f"refs/heads/{SNAPSHOT_BRANCH}"
        if not self._rev_parse(repo_path, ref):
            return []
        raw = self._git(
            repo_path,
            ["log", f"-{limit}", "--format=%H%n%aI%n%s", ref],
        ).strip()
        commits: list[dict[str, Any]] = []
        lines = [ln for ln in raw.splitlines() if ln]
        for i in range(0, len(lines) - 1, 2):
            commits.append(
                {"oid": lines[i], "date": lines[i + 1],
                 "subject": lines[i + 2] if i + 2 < len(lines) else ""}
            )
        return commits

    # --------------------------------------------------------------- internal

    def _capture(self, slug: str, repo_path: Path, start: float) -> dict[str, Any]:
        manifest_path = self.state_dir / f"{slug}.json"
        old_manifest = self._load_manifest(manifest_path)

        tracked, gitlinks = self._ls_tracked(repo_path)
        untracked = self._ls_untracked(repo_path)
        candidate = sorted(set(tracked) | set(untracked) | set(old_manifest))

        entries: dict[str, dict[str, Any]] = {}
        changed: list[str] = []
        added_untracked: list[str] = []
        deleted: list[str] = []
        for rel in candidate:
            if rel in gitlinks:
                continue  # submodules stay opaque
            abs_path = repo_path / rel
            try:
                stat = abs_path.lstat()
            except OSError:
                if rel in old_manifest or rel in tracked:
                    deleted.append(rel)
                continue  # deleted tracked file -> omitted from tree
            mode = self._mode_for(stat)
            if rel in old_manifest:
                prev = old_manifest[rel]
                if (
                    prev.get("mtime_ns") == stat.st_mtime_ns
                    and prev.get("size") == stat.st_size
                    and prev.get("mode") == mode
                ):
                    entries[rel] = prev
                    continue
            oid = self._hash_object(repo_path, rel, abs_path, stat)
            entries[rel] = {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "mode": mode,
                "oid": oid,
            }
            changed.append(rel)
            if rel in untracked:
                added_untracked.append(rel)
        total_changed = len(changed) + len(deleted)

        # Only newly added untracked files are scanned. Tracked files are
        # already part of the repository's history, so snapshotting them adds
        # no exposure; the incremental risk is credential material sitting in
        # fresh, not-yet-committed files (e.g. a stray .env or token dump).
        if added_untracked:
            hits = self._secret_hits(repo_path, added_untracked)
            if hits:
                return {
                    "repo_slug": slug,
                    "repo_path": str(repo_path),
                    "status": "blocked",
                    "commit_oid": None,
                    "files_changed": total_changed,
                    "duration_ms": int((time.monotonic() - start) * 1000),
                    "error": f"secret scan blocked: {', '.join(hits[:5])}",
                }

        tree = self._build_tree(repo_path, entries)
        parent = self._rev_parse(repo_path, f"refs/heads/{SNAPSHOT_BRANCH}")
        msg = f"snapshot {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ({total_changed} changed)"
        commit = self._commit_tree(repo_path, tree, parent, msg)
        if not self._update_ref(repo_path, f"refs/heads/{SNAPSHOT_BRANCH}", commit, parent or ""):
            return {
                "repo_slug": slug,
                "repo_path": str(repo_path),
                "status": "skipped",
                "commit_oid": commit,
                "files_changed": total_changed,
                "duration_ms": int((time.monotonic() - start) * 1000),
                "error": "ref moved concurrently; will retry next cycle",
            }

        self._save_manifest(manifest_path, entries)
        return {
            "repo_slug": slug,
            "repo_path": str(repo_path),
            "status": "success",
            "commit_oid": commit,
            "files_changed": total_changed,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "error": None,
        }

    # ------------------------------------------------------------ git helpers

    def _git(self, repo_path: Path, args: list[str], input_text: str | None = None) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            input=input_text,
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_TIMEOUT,
            env={**os.environ, **GIT_ENV},
        )
        return completed.stdout

    def _git_busy(self, repo_path: Path) -> bool:
        try:
            completed = subprocess.run(
                ["pgrep", "-f", rf"git .*{re.escape(str(repo_path))}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0

    def _ls_tracked(self, repo_path: Path) -> tuple[set[str], set[str]]:
        raw = self._git(repo_path, ["ls-files", "--stage"]).splitlines()
        tracked: set[str] = set()
        gitlinks: set[str] = set()
        for line in raw:
            meta, _, rel = line.partition("\t")
            fields = meta.split()
            if len(fields) >= 1 and fields[0] == "160000":
                gitlinks.add(rel)
            else:
                tracked.add(rel)
        return tracked, gitlinks

    def _ls_untracked(self, repo_path: Path) -> set[str]:
        raw = self._git(repo_path, ["ls-files", "--others", "--exclude-standard"])
        return {ln for ln in raw.splitlines() if ln}

    @staticmethod
    def _mode_for(stat: os.stat_result) -> str:
        if stat_module.S_ISLNK(stat.st_mode):
            return "120000"
        if stat.st_mode & 0o111:
            return "100755"
        return "100644"

    def _hash_object(
        self, repo_path: Path, rel: str, abs_path: Path, stat: os.stat_result
    ) -> str:
        if stat_module.S_ISLNK(stat.st_mode):
            target = os.readlink(abs_path)
            raw = self._git(
                repo_path, ["hash-object", "-w", "--stdin", f"--path={rel}"], input_text=target
            )
        else:
            raw = self._git(
                repo_path, ["hash-object", "-w", f"--path={rel}", str(abs_path)]
            )
        return raw.strip()

    def _secret_hits(self, repo_path: Path, rels: list[str]) -> list[str]:
        hits: list[str] = []
        for rel in rels:
            abs_path = repo_path / rel
            try:
                if abs_path.is_symlink():
                    content = os.readlink(abs_path)
                else:
                    content = abs_path.read_text(errors="ignore")
            except OSError:
                continue
            if any(_line_is_suspicious(line) for line in content.splitlines()):
                hits.append(rel)
        return hits

    def _build_tree(self, repo_path: Path, flat: dict[str, dict[str, Any]]) -> str:
        """Recursively build a full tree object from flat path -> entry maps.

        ``git mktree`` only assembles a single tree level, so nested paths
        must be grouped per directory, with each subdirectory built as its
        own subtree and referenced as a ``040000 tree`` entry.
        """

        def build(prefix: str) -> str:
            blobs: dict[str, tuple[str, str]] = {}  # name -> (mode, oid)
            subdirs: set[str] = set()
            for rel, info in flat.items():
                if not rel.startswith(prefix):
                    continue
                rest = rel[len(prefix):]
                if "/" not in rest:
                    blobs[rest] = (info["mode"], info["oid"])
                else:
                    subdirs.add(rest.split("/", 1)[0])
            lines = []
            for name in sorted(set(blobs) | subdirs):
                if name in subdirs:
                    subtree = build(prefix + name + "/")
                    lines.append(f"040000 tree {subtree}\t{name}")
                else:
                    mode, oid = blobs[name]
                    lines.append(f"{mode} blob {oid}\t{name}")
            return self._git(
                repo_path, ["mktree"], input_text="\n".join(lines) + "\n"
            ).strip()

        return build("")

    def _commit_tree(self, repo_path: Path, tree: str, parent: str | None, msg: str) -> str:
        args = ["commit-tree", tree, "-m", msg]
        if parent:
            args += ["-p", parent]
        env = {
            **os.environ,
            **GIT_ENV,
            "GIT_AUTHOR_NAME": "Substrate Snapshot Bot",
            "GIT_AUTHOR_EMAIL": "snapshot@substrate.local",
            "GIT_COMMITTER_NAME": "Substrate Snapshot Bot",
            "GIT_COMMITTER_EMAIL": "snapshot@substrate.local",
        }
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_TIMEOUT,
            env=env,
        )
        return completed.stdout.strip()

    def _rev_parse(self, repo_path: Path, ref: str) -> str | None:
        try:
            raw = self._git(repo_path, ["rev-parse", "--verify", "--quiet", ref]).strip()
        except subprocess.CalledProcessError:
            return None
        return raw or None

    def _update_ref(self, repo_path: Path, ref: str, new: str, expected: str) -> bool:
        args = ["update-ref", ref, new]
        if expected:
            args.append(expected)
        try:
            self._git(repo_path, args)
            return True
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def _load_manifest(path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _save_manifest(path: Path, manifest: dict[str, dict[str, Any]]) -> None:
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
