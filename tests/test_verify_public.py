import hashlib
import json
import os
from pathlib import Path
import tempfile
import socket
import unittest
from unittest.mock import patch

from scripts.verify_public import verify


class VerifyPublicTest(unittest.TestCase):
    def test_duplicate_json_keys_are_rejected_at_every_manifest_level(self):
        digest = hashlib.sha256(b'source').hexdigest()
        for text in (
                '{"schema_version":2,"schema_version":1,"files":{"source":"' + digest + '"}}',
                '{"schema_version":1,"files":{},"files":{"source":"' + digest + '"}}',
                '{"schema_version":1,"files":{"source":"' + '0' * 64 + '","source":"' + digest + '"}}'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'source').write_bytes(b'source')
                (root / 'PUBLIC_MANIFEST.json').write_text(text)
                for strict in (False, True):
                    with self.assertRaisesRegex(SystemExit, 'integrity failed'):
                        verify(root, strict=strict)

    def test_strict_excludes_git_administration_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'source').write_bytes(b'source')
            (root / 'PUBLIC_MANIFEST.json').write_text(json.dumps({
                'schema_version': 1, 'files': {'source': hashlib.sha256(b'source').hexdigest()}}))
            (root / '.git').mkdir()
            (root / '.git' / 'admin-link').symlink_to('../missing')
            verify(root, strict=True)
            (root / '.git' / 'admin-link').unlink()
            (root / '.git').rmdir()
            (root / '.git').symlink_to('../missing-admin')
            verify(root, strict=True)

    def test_strict_rejects_fifo_and_socket_without_reading_special_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'source').write_bytes(b'source')
            manifest = root / 'PUBLIC_MANIFEST.json'
            manifest.write_text(json.dumps({'schema_version': 1, 'files': {'source': hashlib.sha256(b'source').hexdigest()}}))
            for kind in ('fifo', 'socket'):
                path = root / kind
                with self.subTest(kind=kind), socket.socket(socket.AF_UNIX) as sock:
                    if kind == 'fifo':
                        os.mkfifo(path)
                    else:
                        sock.bind(str(path))
                    read_bytes = Path.read_bytes
                    def regular_bytes(candidate):
                        self.assertNotEqual(candidate, path, 'special file must never be opened')
                        return read_bytes(candidate)
                    with patch.object(Path, 'read_bytes', regular_bytes):
                        verify(root)  # Local unlisted objects do not affect compatible mode.
                        with self.assertRaisesRegex(SystemExit, 'integrity failed'):
                            verify(root, strict=True)
                    path.unlink()
            manifest.unlink()
            os.mkfifo(manifest)
            with patch.object(Path, 'read_text', side_effect=AssertionError('must not read a FIFO')):
                with self.assertRaisesRegex(SystemExit, 'integrity failed'):
                    verify(root, strict=True)

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
