#!/usr/bin/env python3
"""Extract DeviantArt session cookies from the running Chromium profile.

Copies the profile DBs read-only, decrypts cookies via the Safe Storage
key from the OS keyring, and writes a JSON file for the publisher script.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util.Padding import unpad

try:
    import secretstorage
except ImportError:
    secretstorage = None

PROFILE = Path.home() / ".config/chromium/Default"
LOCAL_STATE = Path.home() / ".config/chromium/Local State"

DA_DOMAINS = (".deviantart.com", "deviantart.com")


def get_safe_storage_keys() -> list[bytes]:
    if secretstorage is None:
        raise RuntimeError("secretstorage not available")
    bus = secretstorage.dbus_init()
    collection = secretstorage.get_default_collection(bus)
    collection.unlock()
    keys = []
    for item in collection.get_all_items():
        try:
            if item.get_label() == "Chromium Safe Storage":
                keys.append(item.get_secret())
        except Exception:
            continue
    return keys


def decrypt_value(enc_value: bytes, key: bytes) -> str:
    if enc_value[:3] == b"v10":
        iv, ct = enc_value[3:15], enc_value[15:]
        return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), AES.block_size).decode()
    if enc_value[:3] == b"v11":
        nonce, ct = enc_value[3:15], enc_value[15:]
        return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt(ct).decode()
    return enc_value.decode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default="/tmp/da_cookies.json")
    args = parser.parse_args()

    if not PROFILE.exists():
        print("Chromium Default profile not found", file=sys.stderr)
        return 1

    keys = get_safe_storage_keys()
    if not keys:
        print("Could not retrieve Chromium Safe Storage keys", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        db_copy = Path(tmp) / "Cookies"
        shutil.copy2(PROFILE / "Cookies", db_copy)
        con = sqlite3.connect(db_copy)
        rows = con.execute(
            "SELECT host_key, name, path, encrypted_value, expires_utc, is_secure "
            "FROM cookies WHERE host_key LIKE '%deviantart%'"
        ).fetchall()
        con.close()

    cookies = []
    for host, name, path, enc_val, expires, secure in rows:
        val = None
        for key in keys:
            try:
                val = decrypt_value(enc_val, key)
                break
            except Exception:
                continue
        if val is None:
            continue
        cookies.append({
            "host": host,
            "name": name,
            "path": path,
            "value": val,
            "secure": bool(secure),
            "expires": expires,
        })

    Path(args.output).write_text(json.dumps(cookies, indent=2))
    print(f"Extracted {len(cookies)} deviantart cookies -> {args.output}")
    for c in cookies:
        print(f"  {c['name']} ({c['host']}) secure={c['secure']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
