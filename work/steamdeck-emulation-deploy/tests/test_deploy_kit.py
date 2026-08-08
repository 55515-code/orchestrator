#!/usr/bin/env python3
import csv
import subprocess
import tempfile
from pathlib import Path
from shutil import copytree


KIT = Path(__file__).resolve().parents[1]
SCRIPT = KIT / "deck-emulation-console-deploy.sh"
SYSTEMS = KIT / "config" / "systems.tsv"


def run_cmd(args, cwd=KIT, check=True):
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def test_bash_syntax():
    run_cmd(["bash", "-n", str(SCRIPT)])


def test_systems_manifest_has_expected_shape():
    with SYSTEMS.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert len(rows) >= 20
    assert {"key", "display_name", "tier", "default_collection", "storage_hint", "bios_posture", "notes"} == set(rows[0])
    assert any(row["key"] == "ps2" and row["storage_hint"] == "internal" for row in rows)
    assert any(row["default_collection"] == "Experimental" for row in rows)
    assert len({row["key"] for row in rows}) == len(rows)
    assert all(row["key"].replace("-", "").isalnum() for row in rows)
    assert all(row["storage_hint"] in {"internal", "microsd"} for row in rows)


def test_dry_run_does_not_create_target():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "dry-run-root"
        result = run_cmd([str(SCRIPT), "--dry-run", "--mode", "emudeck", "--root", str(root)])
        assert "Dry run complete" in result.stdout
        assert not root.exists()


def test_apply_creates_deck_ready_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "Emulation"
        result = run_cmd([str(SCRIPT), "--apply", "--mode", "emudeck", "--root", str(root)])

        assert "Ready:" in result.stdout
        assert (root / "bios").is_dir()
        assert (root / "roms" / "ps2").is_dir()
        assert (root / "roms" / "wiiu").is_dir()
        assert (root / "docs" / "DEPLOYMENT-CHECKLIST.md").is_file()
        assert (root / "docs" / "SYSTEMS-MANIFEST.md").is_file()
        assert (root / "docs" / "QUICKSTART.md").is_file()
        assert (root / "docs" / "READINESS-REPORT.md").is_file()
        assert (root / "docs" / "ACCEPTANCE.md").is_file()
        assert (root / "docs" / "test-log.tsv").is_file()

        checklist = (root / "docs" / "DEPLOYMENT-CHECKLIST.md").read_text()
        manifest = (root / "docs" / "SYSTEMS-MANIFEST.md").read_text()
        quickstart = (root / "docs" / "QUICKSTART.md").read_text()
        report = (root / "docs" / "READINESS-REPORT.md").read_text()
        acceptance = (root / "docs" / "ACCEPTANCE.md").read_text()
        test_log = (root / "docs" / "test-log.tsv").read_text()

        assert "ES-DE launches from Gaming Mode" in checklist
        assert 'EMULATION_ROOT="$(cd ../.. && pwd)"' in checklist
        assert "This kit never provides ROMs, BIOS files, firmware, keys, or DRM bypass steps." in checklist
        assert "| `ps3` | PlayStation 3 |" in manifest
        assert "Do not add the full ROM library directly to Steam" in quickstart
        assert 'EMULATION_ROOT="$(cd ../.. && pwd)"' in quickstart
        assert "../../docs/DEPLOYMENT-CHECKLIST.md" in quickstart
        assert "Systems prepared:" in report
        assert "- READINESS-REPORT.md" in report
        assert "- ACCEPTANCE.md" in report
        assert "ES-DE launches from Steam Gaming Mode" in acceptance
        assert "No ROM, BIOS, firmware, key, or bypass-source notes are stored in this kit." in acceptance
        assert test_log.startswith("date\tsystem\tgame\temulator")


def test_retrodeck_mode_writes_retrodeck_guidance():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "RetroDeck"
        run_cmd([str(SCRIPT), "--apply", "--mode", "retrodeck", "--root", str(root)])
        checklist = (root / "docs" / "DEPLOYMENT-CHECKLIST.md").read_text()
        assert "RetroDECK mode" in checklist
        assert "Flathub/Discover" in checklist


def test_apply_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "Emulation"
        run_cmd([str(SCRIPT), "--apply", "--mode", "emudeck", "--root", str(root)])
        run_cmd([str(SCRIPT), "--apply", "--mode", "emudeck", "--root", str(root)])
        assert (root / "roms" / "ps2").is_dir()
        assert (root / "docs" / "READINESS-REPORT.md").read_text().count("Systems prepared:") == 1


def test_rejects_bad_arguments_and_dangerous_roots():
    bad_mode = run_cmd([str(SCRIPT), "--mode", "bad"], check=False)
    assert bad_mode.returncode != 0
    assert "--mode must be emudeck or retrodeck" in bad_mode.stderr

    bad_root = run_cmd([str(SCRIPT), "--root", "/"], check=False)
    assert bad_root.returncode != 0
    assert "--root cannot be /" in bad_root.stderr


def test_missing_or_invalid_systems_file_fails_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        copied = Path(tmp) / "kit"
        copytree(KIT, copied)
        systems = copied / "config" / "systems.tsv"
        systems.write_text("bad\theader\n")
        result = run_cmd([str(copied / "deck-emulation-console-deploy.sh"), "--dry-run"], cwd=copied, check=False)
        assert result.returncode != 0
        assert "unexpected systems.tsv header" in result.stderr


if __name__ == "__main__":
    tests = [
        test_bash_syntax,
        test_systems_manifest_has_expected_shape,
        test_dry_run_does_not_create_target,
        test_apply_creates_deck_ready_artifacts,
        test_retrodeck_mode_writes_retrodeck_guidance,
        test_apply_is_idempotent,
        test_rejects_bad_arguments_and_dangerous_roots,
        test_missing_or_invalid_systems_file_fails_cleanly,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
