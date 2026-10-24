import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.verify_public import verify


class VerifyPublicTest(unittest.TestCase):
    def test_valid_release_then_changed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'evidence.txt').write_bytes(b'evidence')
            manifest = {'files': {'evidence.txt': hashlib.sha256(b'evidence').hexdigest()}}
            (root / 'PUBLIC_MANIFEST.json').write_text(json.dumps(manifest))
            verify(root)
            (root / 'evidence.txt').write_bytes(b'changed')
            with self.assertRaisesRegex(SystemExit, 'integrity failed'):
                verify(root)

    def test_manifest_cannot_escape_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'PUBLIC_MANIFEST.json').write_text(json.dumps({'files': {'../outside': 'hash'}}))
            with self.assertRaisesRegex(SystemExit, 'integrity failed'):
                verify(root)


if __name__ == '__main__':
    unittest.main()
