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
            manifest = {'schema_version': 1, 'files': {'evidence.txt': hashlib.sha256(b'evidence').hexdigest()}}
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

    def test_manifest_schema_is_nonempty_and_hashes_and_paths_are_canonical(self):
        invalid = [None, [], {}, {'files': {}}, {'schema_version': 1, 'files': {}},
                   {'schema_version': 2, 'files': {'a': '0' * 64}},
                   {'schema_version': 1, 'files': {'a': 'bad'}}]
        invalid += [{'schema_version': 1, 'files': {name: '0' * 64}}
                    for name in ('', '/absolute', '../escape', './a', 'a//b', 'a/../b', 'a\\b', 'PUBLIC_MANIFEST.json')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for manifest in invalid:
                with self.subTest(manifest=manifest):
                    (root / 'PUBLIC_MANIFEST.json').write_text(json.dumps(manifest))
                    with self.assertRaisesRegex(SystemExit, 'integrity failed'):
                        verify(root)

    def test_strict_rejects_unlisted_files_and_omitted_entries_but_normal_allows_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'source.py').write_bytes(b'source')
            manifest = {'schema_version': 1, 'files': {'source.py': hashlib.sha256(b'source').hexdigest()}}
            (root / 'PUBLIC_MANIFEST.json').write_text(json.dumps(manifest))
            (root / '.git').mkdir()
            (root / '.git' / 'config').write_text('local only')
            verify(root, strict=True)
            for name in ('inventory_llm/extra.py', '.env.accidental', 'outputs/synthetic_demo/detail.json'):
                extra = root / name
                extra.parent.mkdir(parents=True, exist_ok=True)
                extra.write_text('extra')
                verify(root)
                with self.assertRaisesRegex(SystemExit, 'integrity failed'):
                    verify(root, strict=True)
                extra.unlink()
            (root / 'omitted.py').write_text('omitted required source')
            with self.assertRaisesRegex(SystemExit, 'integrity failed'):
                verify(root, strict=True)

    def test_strict_rejects_file_directory_and_dangling_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'source').write_bytes(b'source')
            (root / 'PUBLIC_MANIFEST.json').write_text(json.dumps({
                'schema_version': 1, 'files': {'source': hashlib.sha256(b'source').hexdigest()}}))
            for target in ('source', '.', 'missing'):
                link = root / 'link'
                link.symlink_to(target)
                with self.assertRaisesRegex(SystemExit, 'integrity failed'):
                    verify(root, strict=True)
                link.unlink()


if __name__ == '__main__':
    unittest.main()
