"""Independent recovery verification. All writes are inside temporary test folders."""
import hashlib
import io
import json
import sqlite3
import stat
import subprocess
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch
from coordinator import Coordinator, Conflict
import verify_backup as recovery

class ReviewRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='independent-recovery-')
        self.root = Path(self.tmp.name)
        self.archive = self.root / 'backup.zip'
        self.dest = self.root / 'new-restored-source'
        self.payload = {name: b'# inert isolated test fixture\n' for name in recovery.BASE}
        self.payload['README.md'] = b'verified-original'
    def tearDown(self): self.tmp.cleanup()
    def make_archive(self, payload=None, manifest=None, extra_entries=()):
        payload = self.payload if payload is None else payload
        manifest = {n: hashlib.sha256(v).hexdigest() for n, v in payload.items()} if manifest is None else manifest
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                for name, value in payload.items(): z.writestr(name, value)
                z.writestr('MANIFEST.json', json.dumps(manifest))
                for name, value in extra_entries: z.writestr(name, value)
        return buffer.getvalue()
    def prepare(self, data):
        self.archive.write_bytes(data)
        return hashlib.sha256(data).hexdigest()
    def reject_before_execute(self, data, exceptions=(ValueError, KeyError, zipfile.BadZipFile)):
        expected = self.prepare(data)
        with patch.object(recovery.subprocess, 'run') as run:
            with self.assertRaises(exceptions): recovery.restore(self.archive, expected, self.dest)
            run.assert_not_called()
        self.assertFalse(self.dest.exists())
    def test_verified_archive_bytes_are_the_bytes_consumed(self):
        original = self.make_archive()
        forged_payload = dict(self.payload, **{'README.md': b'replaced-after-hash-check'})
        replacement = self.make_archive(forged_payload)
        expected = self.prepare(original)
        real_zipfile = zipfile.ZipFile
        def replace_before_reopen(file, *args, **kwargs):
            # Simulate archive replacement after SHA verification but before parsing.
            self.archive.write_bytes(replacement)
            return real_zipfile(file, *args, **kwargs)
        with patch.object(recovery.zipfile, 'ZipFile', side_effect=replace_before_reopen):
            with patch.object(recovery.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                result = recovery.restore(self.archive, expected, self.dest)
        self.assertEqual((self.dest / 'README.md').read_bytes(), b'verified-original')
        self.assertEqual(result['sha256'], expected)
    def test_manifest_mismatch_fails_before_destination_creation(self):
        manifest = {n: hashlib.sha256(v).hexdigest() for n,v in self.payload.items()}
        manifest['README.md'] = '0' * 64
        self.reject_before_execute(self.make_archive(manifest=manifest))
    def test_duplicate_manifest_key_is_rejected(self):
        buffer=io.BytesIO()
        manifest={n:hashlib.sha256(v).hexdigest() for n,v in self.payload.items()}
        body=json.dumps(manifest)
        body=body[:-1]+', "README.md": '+json.dumps(manifest['README.md'])+'}'
        with zipfile.ZipFile(buffer,'w') as z:
            for name,value in self.payload.items():z.writestr(name,value)
            z.writestr('MANIFEST.json',body)
        self.reject_before_execute(buffer.getvalue())
    def test_missing_manifest_member_fails_before_extraction(self):
        manifest = {n: hashlib.sha256(v).hexdigest() for n,v in self.payload.items()}
        del manifest['README.md']
        self.reject_before_execute(self.make_archive(manifest=manifest))
    def test_duplicate_allowed_path_is_rejected(self):
        self.reject_before_execute(self.make_archive(extra_entries=[('README.md', b'duplicate')]))
    def test_path_traversal_and_absolute_paths_are_rejected(self):
        for path in ('../escaped', '/tmp/escaped', 'tests/../../escaped', 'tests\\..\\escaped'):
            with self.subTest(path=path): self.reject_before_execute(self.make_archive(extra_entries=[(path,b'bad')]))
        self.assertFalse((self.root/'escaped').exists())
    def test_symlink_with_allowed_name_is_rejected(self):
        payload = dict(self.payload); del payload['README.md']
        info = zipfile.ZipInfo('README.md'); info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        manifest = {n:hashlib.sha256(v).hexdigest() for n,v in self.payload.items()}
        self.reject_before_execute(self.make_archive(payload, manifest, [(info,b'/outside')]))
    def test_decompression_size_limit_precedes_extraction(self):
        payload = dict(self.payload, **{'README.md': b'x' * 8_000_001})
        self.reject_before_execute(self.make_archive(payload))
    def test_invalid_hash_never_calls_subprocess(self):
        self.prepare(self.make_archive())
        with patch.object(recovery.subprocess, 'run') as run:
            with self.assertRaises(ValueError): recovery.restore(self.archive, '0' * 64, self.dest)
            run.assert_not_called()
        self.assertFalse(self.dest.exists())
    def test_existing_destination_and_dangling_symlink_are_rejected(self):
        expected=self.prepare(self.make_archive()); self.dest.mkdir()
        marker=self.dest/'preserved.txt'; marker.write_text('unchanged')
        with self.assertRaises(ValueError): recovery.restore(self.archive,expected,self.dest)
        self.assertEqual(marker.read_text(),'unchanged')
        dangling=self.root/'dangling'; dangling.symlink_to(self.root/'absent-target',target_is_directory=True)
        with self.assertRaises((ValueError, FileExistsError)): recovery.restore(self.archive,expected,dangling)
        self.assertFalse((self.root/'absent-target').exists())
    def test_test_failure_never_reports_success(self):
        expected=self.prepare(self.make_archive())
        with patch.object(recovery.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','fixture failure')) as run:
            with self.assertRaises(RuntimeError): recovery.restore(self.archive,expected,self.dest)
        self.assertEqual(run.call_count,1)
    def test_missing_db_is_not_created(self):
        missing=self.root/'not-a-live-db.db'
        with self.assertRaises(sqlite3.Error): Coordinator(missing).status()
        self.assertFalse(missing.exists())
    def test_new_epoch_rejects_old_token_and_preserves_unknown_inventory(self):
        old=Coordinator(self.root/'old-isolated.db'); old.initialize('review-mock',True)
        token=old.execute('acquire','old-acquire','worker')['owner']['token']
        new=Coordinator(self.root/'new-isolated.db'); new.initialize('review-mock',True)
        fresh=new.execute('acquire','new-acquire','worker')['owner']['token']
        self.assertNotEqual(token,fresh)
        with self.assertRaises(Conflict): new.execute('begin','stale-begin','worker',token=token,action='old-action')
        self.assertFalse(new.status()['inventory_complete']); self.assertIsNone(new.status()['active'])
if __name__ == '__main__': unittest.main(verbosity=2)
