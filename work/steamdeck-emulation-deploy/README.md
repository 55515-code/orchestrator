# Steam Deck Emulation Console Deploy Kit

This kit turns the research package into a simple, Deck-ready preparation step for an **ES-DE-first emulation console**.

It prepares folders, system manifests, source links, and the final checklist. It does **not** download ROMs, BIOS files, firmware, keys, or bypass tools.

## Fast Path on the Steam Deck

1. Copy `work/steamdeck-emulation-deploy/` to the Deck.
2. Open Desktop Mode and run:

   ```bash
   cd steamdeck-emulation-deploy
   ./deck-emulation-console-deploy.sh --apply --mode emudeck --root "$HOME/Emulation"
   ```

3. Open:

   ```text
   $HOME/Emulation/docs/QUICKSTART.md
   ```

4. Follow `DEPLOYMENT-CHECKLIST.md` to install EmuDeck, configure ES-DE, run BIOS checks, scrape metadata, and complete handheld/docked validation.

## Local Dry Run

From this workspace:

```bash
./work/steamdeck-emulation-deploy/deck-emulation-console-deploy.sh --dry-run --mode emudeck --root /tmp/deck-emulation-demo
```

## Modes

- `--mode emudeck`: recommended default. Prepares for EmuDeck + ES-DE + selective Steam ROM Manager.
- `--mode retrodeck`: appliance alternative. Prepares the same library structure and points the checklist toward RetroDECK/Flathub.

## What Gets Created

- `bios/`
- `roms/<system>/`
- `saves/`
- `tools/`
- `media/`
- `backups/`
- `docs/DEPLOYMENT-CHECKLIST.md`
- `docs/SYSTEMS-MANIFEST.md`
- `docs/QUICKSTART.md`
- `docs/READINESS-REPORT.md`
- `docs/ACCEPTANCE.md`
- `docs/test-log.tsv`
- `docs/source-links.txt`

## Validation

Run the local verifier:

```bash
python3 work/steamdeck-emulation-deploy/tests/test_deploy_kit.py
```

The test checks shell syntax, config validation, dry-run behavior, apply behavior in a temporary directory, generated docs, idempotency, bad-argument failures, and legal-safety wording.
