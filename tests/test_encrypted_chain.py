from __future__ import annotations

import unittest
from pathlib import Path

from substrate.encrypted_chain import (
    DecryptionError,
    EncryptedChainContext,
    EncryptedChainRegistry,
    EncryptionError,
    decrypt_with_private,
    encrypt_for_peer,
    generate_chain_keypair,
)


class TestKeyPairGeneration(unittest.TestCase):
    def test_generate_chain_keypair_returns_valid_pem(self) -> None:
        keypair = generate_chain_keypair("test-chain")
        self.assertEqual("test-chain", keypair.chain_id)
        self.assertTrue(keypair.private_key_pem.startswith(b"-----BEGIN"))
        self.assertTrue(keypair.public_key_pem.startswith(b"-----BEGIN"))

    def test_keypair_roundtrip(self) -> None:
        keypair = generate_chain_keypair("roundtrip")
        plaintext = b"hello encrypted world"
        ciphertext = encrypt_for_peer(plaintext, keypair.public_key_pem)
        recovered = decrypt_with_private(ciphertext, keypair.private_key_pem)
        self.assertEqual(plaintext, recovered)


class TestEncryptedChainContext(unittest.TestCase):
    def test_create_context(self) -> None:
        context = EncryptedChainContext(
            chain_id="ctx-1",
            keypair=generate_chain_keypair("ctx-1"),
        )
        self.assertEqual("ctx-1", context.chain_id)

    def test_encrypt_and_decrypt_step_payload(self) -> None:
        context = EncryptedChainContext(
            chain_id="ctx-2",
            keypair=generate_chain_keypair("ctx-2"),
        )
        payload = {"prompt": "secret prompt", "run_id": "run-123"}
        ciphertext = context.encrypt_step_payload("step-1", payload)
        self.assertIsInstance(ciphertext, bytes)
        recovered = context.decrypt_step_payload(ciphertext)
        self.assertEqual(payload, recovered)

    def test_register_peer_and_encrypt_for_peer(self) -> None:
        context = EncryptedChainContext(
            chain_id="ctx-3",
            keypair=generate_chain_keypair("ctx-3"),
        )
        peer_keypair = generate_chain_keypair("peer-1")
        context.register_peer("peer-1", peer_keypair.public_key_pem)
        plaintext = b"peer secret"
        ciphertext = context.encrypt_for_peer("peer-1", plaintext)
        recovered = decrypt_with_private(ciphertext, peer_keypair.private_key_pem)
        self.assertEqual(plaintext, recovered)

    def test_encrypt_for_unknown_peer_raises(self) -> None:
        context = EncryptedChainContext(
            chain_id="ctx-4",
            keypair=generate_chain_keypair("ctx-4"),
        )
        with self.assertRaises(EncryptionError):
            context.encrypt_for_peer("unknown", b"data")

    def test_public_bundle(self) -> None:
        context = EncryptedChainContext(
            chain_id="ctx-5",
            keypair=generate_chain_keypair("ctx-5"),
        )
        bundle = context.public_bundle()
        self.assertEqual("ctx-5", bundle["chain_id"])
        self.assertIn("public_key_pem", bundle)
        self.assertIn("peers", bundle)

    def test_key_rotation(self) -> None:
        context = EncryptedChainContext(
            chain_id="ctx-6",
            keypair=generate_chain_keypair("ctx-6"),
        )
        old_public = context.keypair.public_key_pem
        new_keypair = context.rotate_key()
        self.assertNotEqual(old_public, new_keypair.public_key_pem)

    def test_decrypt_invalid_envelope_raises(self) -> None:
        context = EncryptedChainContext(
            chain_id="ctx-7",
            keypair=generate_chain_keypair("ctx-7"),
        )
        with self.assertRaises(DecryptionError):
            context.decrypt_step_payload(b"not valid ciphertext")


class TestEncryptedChainRegistry(unittest.TestCase):
    def test_create_and_get_chain(self) -> None:
        with unittest.TestCase().subTest():
            pass
        with tempfile.TemporaryDirectory() as tmp:
            registry = EncryptedChainRegistry(Path(tmp))
            context = registry.create_chain("chain-1")
            self.assertEqual("chain-1", context.chain_id)
            loaded = registry.get_chain("chain-1")
            self.assertIsNotNone(loaded)
            self.assertEqual("chain-1", loaded.chain_id)

    def test_get_missing_chain_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = EncryptedChainRegistry(Path(tmp))
            self.assertIsNone(registry.get_chain("missing"))

    def test_register_peer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = EncryptedChainRegistry(Path(tmp))
            registry.create_chain("chain-2")
            peer_keypair = generate_chain_keypair("peer-2")
            registry.register_peer("chain-2", "peer-2", peer_keypair.public_key_pem)
            context = registry.get_chain("chain-2")
            assert context is not None
            self.assertIn("peer-2", context.peer_public_keys)

    def test_rotate_chain_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = EncryptedChainRegistry(Path(tmp))
            registry.create_chain("chain-3")
            old_key = registry.get_chain("chain-3").keypair.public_key_pem
            new_keypair = registry.rotate_chain_key("chain-3")
            self.assertNotEqual(old_key, new_keypair.public_key_pem)

    def test_persistence_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry1 = EncryptedChainRegistry(Path(tmp))
            registry1.create_chain("chain-4")
            registry2 = EncryptedChainRegistry(Path(tmp))
            context = registry2.get_chain("chain-4")
            self.assertIsNotNone(context)
            self.assertEqual("chain-4", context.chain_id)


import tempfile

if __name__ == "__main__":
    unittest.main()
