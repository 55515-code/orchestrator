from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

_RSA_KEY_SIZE = 2048
_AES_KEY_SIZE = 32
_AES_NONCE_SIZE = 16
_PBKDF2_ITERATIONS = 100_000
_MAX_CIPHERTEXT_SIZE = 64 * 1024


class EncryptionError(Exception):
    pass


class DecryptionError(Exception):
    pass


@dataclass(slots=True)
class ChainKeyPair:
    chain_id: str
    private_key_pem: bytes
    public_key_pem: bytes
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def private_key(self):
        return serialization.load_pem_private_key(self.private_key_pem, password=None)

    def public_key(self):
        return serialization.load_pem_public_key(self.public_key_pem)


def generate_chain_keypair(chain_id: str) -> ChainKeyPair:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=_RSA_KEY_SIZE)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return ChainKeyPair(
        chain_id=chain_id,
        private_key_pem=private_key_pem,
        public_key_pem=public_key_pem,
    )


def _derive_aes_key(shared_secret: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_AES_KEY_SIZE,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(shared_secret)


def _encrypt_aes_gcm(plaintext: bytes, key: bytes) -> bytes:
    nonce = os.urandom(_AES_NONCE_SIZE)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    return nonce + encryptor.tag + ciphertext


def _decrypt_aes_gcm(ciphertext: bytes, key: bytes) -> bytes:
    if len(ciphertext) < _AES_NONCE_SIZE + 16:
        raise DecryptionError("Ciphertext too short")
    nonce = ciphertext[:_AES_NONCE_SIZE]
    tag = ciphertext[_AES_NONCE_SIZE:_AES_NONCE_SIZE + 16]
    encrypted = ciphertext[_AES_NONCE_SIZE + 16:]
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
    decryptor = cipher.decryptor()
    return decryptor.update(encrypted) + decryptor.finalize()


def encrypt_for_peer(plaintext: bytes, peer_public_key_pem: bytes) -> bytes:
    peer_public_key = serialization.load_pem_public_key(peer_public_key_pem)
    aes_key = os.urandom(_AES_KEY_SIZE)
    encrypted_aes_key = peer_public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    encrypted_payload = _encrypt_aes_gcm(plaintext, aes_key)
    return encrypted_aes_key + encrypted_payload


def decrypt_with_private(ciphertext: bytes, private_key_pem: bytes) -> bytes:
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    aes_key_size = private_key.key_size // 8
    if len(ciphertext) < aes_key_size:
        raise DecryptionError("Ciphertext too short for RSA-encrypted AES key")
    encrypted_aes_key = ciphertext[:aes_key_size]
    encrypted_payload = ciphertext[aes_key_size:]
    try:
        aes_key = private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except ValueError as exc:
        raise DecryptionError(f"RSA decryption failed: {exc}") from exc
    return _decrypt_aes_gcm(encrypted_payload, aes_key)


@dataclass(slots=True)
class EncryptedChainContext:
    chain_id: str
    keypair: ChainKeyPair
    peer_public_keys: dict[str, bytes] = field(default_factory=dict)
    key_rotation_interval_seconds: int = 3600
    _last_rotation: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def register_peer(self, peer_id: str, public_key_pem: bytes) -> None:
        self.peer_public_keys[peer_id] = public_key_pem

    def rotate_key(self) -> ChainKeyPair:
        self.keypair = generate_chain_keypair(self.chain_id)
        self._last_rotation = datetime.now(timezone.utc).timestamp()
        return self.keypair

    def maybe_rotate(self) -> None:
        now = datetime.now(timezone.utc).timestamp()
        if now - self._last_rotation >= self.key_rotation_interval_seconds:
            self.rotate_key()

    def encrypt_for_peer(self, peer_id: str, plaintext: bytes) -> bytes:
        peer_key = self.peer_public_keys.get(peer_id)
        if peer_key is None:
            raise EncryptionError(f"No public key registered for peer '{peer_id}'")
        return encrypt_for_peer(plaintext, peer_key)

    def encrypt_step_payload(self, step_id: str, payload: dict[str, Any]) -> bytes:
        plaintext = json.dumps({"step_id": step_id, "payload": payload}, ensure_ascii=False).encode("utf-8")
        if len(plaintext) > _MAX_CIPHERTEXT_SIZE:
            raise EncryptionError(f"Step payload too large: {len(plaintext)} bytes")
        return encrypt_for_peer(plaintext, self.keypair.public_key_pem)

    def decrypt_step_payload(self, ciphertext: bytes) -> dict[str, Any]:
        plaintext = decrypt_with_private(ciphertext, self.keypair.private_key_pem)
        envelope = json.loads(plaintext.decode("utf-8"))
        if not isinstance(envelope, dict) or "payload" not in envelope:
            raise DecryptionError("Invalid encrypted step envelope")
        return envelope["payload"]

    def public_bundle(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "public_key_pem": self.keypair.public_key_pem.decode("utf-8"),
            "created_at": self.keypair.created_at,
            "peers": sorted(self.peer_public_keys.keys()),
        }


class EncryptedChainRegistry:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._contexts: dict[str, EncryptedChainContext] = {}
        self._lock = threading.Lock()

    def _context_path(self, chain_id: str) -> Path:
        return self.storage_dir / f"{chain_id}.json"

    def create_chain(self, chain_id: str) -> EncryptedChainContext:
        with self._lock:
            if chain_id in self._contexts:
                return self._contexts[chain_id]
            keypair = generate_chain_keypair(chain_id)
            context = EncryptedChainContext(chain_id=chain_id, keypair=keypair)
            self._contexts[chain_id] = context
            self._persist(context)
            return context

    def get_chain(self, chain_id: str) -> EncryptedChainContext | None:
        with self._lock:
            if chain_id in self._contexts:
                return self._contexts[chain_id]
            path = self._context_path(chain_id)
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            context = EncryptedChainContext(
                chain_id=data["chain_id"],
                keypair=ChainKeyPair(
                    chain_id=data["chain_id"],
                    private_key_pem=data["keypair"]["private_key_pem"].encode("utf-8"),
                    public_key_pem=data["keypair"]["public_key_pem"].encode("utf-8"),
                    created_at=data["keypair"]["created_at"],
                ),
                peer_public_keys={
                    k: v.encode("utf-8") for k, v in data.get("peer_public_keys", {}).items()
                },
                key_rotation_interval_seconds=data.get("key_rotation_interval_seconds", 3600),
                _last_rotation=data.get("last_rotation", datetime.now(timezone.utc).timestamp()),
            )
            self._contexts[chain_id] = context
            return context

    def register_peer(self, chain_id: str, peer_id: str, public_key_pem: bytes) -> None:
        context = self.get_chain(chain_id)
        if context is None:
            raise KeyError(f"Chain '{chain_id}' not found")
        context.register_peer(peer_id, public_key_pem)
        self._persist(context)

    def rotate_chain_key(self, chain_id: str) -> ChainKeyPair:
        context = self.get_chain(chain_id)
        if context is None:
            raise KeyError(f"Chain '{chain_id}' not found")
        keypair = context.rotate_key()
        self._persist(context)
        return keypair

    def _persist(self, context: EncryptedChainContext) -> None:
        path = self._context_path(context.chain_id)
        data = {
            "chain_id": context.chain_id,
            "keypair": {
                "private_key_pem": context.keypair.private_key_pem.decode("utf-8"),
                "public_key_pem": context.keypair.public_key_pem.decode("utf-8"),
                "created_at": context.keypair.created_at,
            },
            "peer_public_keys": {
                k: v.decode("utf-8") for k, v in context.peer_public_keys.items()
            },
            "key_rotation_interval_seconds": context.key_rotation_interval_seconds,
            "last_rotation": context._last_rotation,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
