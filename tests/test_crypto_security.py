from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from substrate.security import AbuseDetector, AuditTrail, RateLimiter


class AuditTrailTest(unittest.TestCase):
    def test_append_verify_and_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trail = AuditTrail(Path(tmp) / "audit.jsonl")
            trail.append("wallet_generated", tier=2, details={"purpose": "donations"})
            trail.append("backup_verified", tier=1, details={"ok": True})
            report = trail.verify()
            self.assertTrue(report["ok"])
            self.assertEqual(2, report["count"])
            self.assertEqual(2, len(trail.tail(5)))

    def test_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            trail = AuditTrail(path)
            trail.append("payment_verified", tier=1)
            trail.append("delivered", tier=1)
            trail.append("another", tier=0)
            lines = path.read_text(encoding="utf-8").splitlines()
            payload = lines[0]
            mutated = payload.replace('"tier": 1', '"tier": 0', 1)
            lines[0] = mutated
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report = trail.verify()
            self.assertFalse(report["ok"])
            self.assertTrue(any("hash mismatch" in e for e in report["errors"]))

    def test_removed_record_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            trail = AuditTrail(path)
            trail.append("one", tier=0)
            trail.append("two", tier=0)
            trail.append("three", tier=0)
            lines = path.read_text(encoding="utf-8").splitlines()
            del lines[1]  # remove the middle record
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report = trail.verify()
            self.assertFalse(report["ok"])
            self.assertTrue(any("prev_hash mismatch" in e for e in report["errors"]))


class RateLimiterTest(unittest.TestCase):
    def test_sliding_window(self) -> None:
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        self.assertTrue(limiter.allow("ip:1.2.3.4", now=1000.0))
        self.assertTrue(limiter.allow("ip:1.2.3.4", now=1001.0))
        self.assertFalse(limiter.allow("ip:1.2.3.4", now=1002.0))
        # After 60s the earliest stamp expires, freeing one slot.
        self.assertTrue(limiter.allow("ip:1.2.3.4", now=1062.0))
        self.assertEqual(1, limiter.remaining("ip:1.2.3.4", now=1062.0))

    def test_persists_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "limits.json"
            first = RateLimiter(max_requests=5, state_path=state)
            first.allow("wallet:0xabc", now=100.0)
            second = RateLimiter(max_requests=5, state_path=state)
            self.assertTrue(second.allow("wallet:0xabc", now=120.0))
            self.assertEqual(3, second.remaining("wallet:0xabc", now=120.0))


class AbuseDetectorTest(unittest.TestCase):
    def test_ip_rate_limit_flags_review(self) -> None:
        detector = AbuseDetector(
            ip_limiter=RateLimiter(max_requests=2, window_seconds=60),
        )
        detector.check_request("9.9.9.9", resource_id="r1", paid=True, now=10.0)
        detector.check_request("9.9.9.9", resource_id="r1", paid=True, now=11.0)
        allowed, reason = detector.check_request("9.9.9.9", resource_id="r1", paid=True, now=12.0)
        self.assertFalse(allowed)
        self.assertEqual("ip_rate_limited", reason)
        self.assertTrue(any(f["reason"] == "ip_rate_limited" for f in detector.flags()))

    def test_unpaid_paid_resource_blocked(self) -> None:
        detector = AbuseDetector()
        allowed, reason = detector.check_request(
            "1.1.1.1", resource_id="paid-resource", paid=False, is_paid_resource=True, now=10.0
        )
        self.assertFalse(allowed)
        self.assertEqual("payment_required", reason)

    def test_download_burst_detected(self) -> None:
        detector = AbuseDetector(burst_limit=3)
        for stamp in (10.0, 11.0, 12.0, 13.0):
            allowed, _ = detector.check_request("2.2.2.2", resource_id="r2", paid=True, now=stamp)
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
