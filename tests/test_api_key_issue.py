"""Pins the API key format shared with vepathos-api-doc.

Both this repo's CLI (`scripts/issue_api_key.py`) and api-doc's
`routehub-api-key-crypto.ts` write to the same `api_key` table, and
`libs/authorization` resolves a request by `key_hash` alone. If either side
changes the prefix, the entropy or the hash, keys minted by one stop
authenticating through the other — silently. These tests fail instead.
"""

import hashlib
import os
import sys
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.authorization.authorization import API_KEY_PREFIX, hash_api_key
from scripts.issue_api_key import RESERVED_NAMES, generate_api_key


class TestApiKeyFormatContract(unittest.TestCase):
    def test_prefix_matches_api_doc(self):
        # api-doc: ROUTEHUB_API_KEY_PREFIX = "rh_live_"
        self.assertEqual(API_KEY_PREFIX, "rh_live_")

    def test_raw_key_shape(self):
        raw, _, _ = generate_api_key()
        self.assertTrue(raw.startswith("rh_live_"))
        # api-doc: randomBytes(24).toString("base64url") -> 32 unpadded chars.
        self.assertEqual(len(raw), len("rh_live_") + 32)
        self.assertNotIn("=", raw)
        self.assertNotIn("+", raw)
        self.assertNotIn("/", raw)

    def test_hash_is_plain_sha256_hex_of_the_raw_key(self):
        # api-doc: createHash("sha256").update(raw, "utf8").digest("hex")
        raw, key_hash, _ = generate_api_key()
        self.assertEqual(key_hash, hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(key_hash, hash_api_key(raw))
        self.assertEqual(len(key_hash), 64)

    def test_key_prefix_is_first_12_chars(self):
        # api-doc: raw.slice(0, 12) — must fit api_key.key_prefix varchar(16).
        raw, _, key_prefix = generate_api_key()
        self.assertEqual(key_prefix, raw[:12])
        self.assertLessEqual(len(key_prefix), 16)

    def test_keys_are_unique(self):
        keys = {generate_api_key()[0] for _ in range(100)}
        self.assertEqual(len(keys), 100)

    def test_api_doc_owned_names_are_reserved(self):
        # api-doc revokes by (company_id, name) on rotation, so a CLI key under
        # either name would be revoked out from under its owner.
        self.assertIn("vepathos-api-doc", RESERVED_NAMES)
        self.assertIn("api-doc local dev", RESERVED_NAMES)


if __name__ == "__main__":
    unittest.main()
