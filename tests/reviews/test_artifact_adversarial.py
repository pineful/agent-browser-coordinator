"""Twelve independent-review checks retained as reproducible release regressions."""
import hashlib
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from agent_browser_coordinator import Coordinator, VERSION
from scripts import verify_backup, verify_install

ROOT = Path(__file__).resolve().parents[2]

class ArtifactAdversarialReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='abc-adversarial-')
        self.root = Path(self.temp.name)
        self.payload = {n: b'# inert fixture\n' for n in verify_backup.BASE}
        self.original = dict(self.payload)
        self.original['MANIFEST.json'] = json.dumps({n: hashlib.sha256(b).hexdigest() for n,b in self.payload.items()}).encode()
    def tearDown(self):
        self.temp.cleanup()
    def reject_zip(self, changes, symlink=None):
        contents = dict(self.original)
        changes(contents)
        out = self.root / 'archive.zip'
        with zipfile.ZipFile(out, 'w') as z:
            for n,b in contents.items():
                if n == symlink:
                    info = zipfile.ZipInfo(n)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    z.writestr(info,b)
                else:
                    z.writestr(n,b)
        dest = self.root / 'restore'
        with patch.object(verify_backup.subprocess,'run') as run:
            with self.assertRaises((ValueError,KeyError)):
                verify_backup.restore(out,hashlib.sha256(out.read_bytes()).hexdigest(),dest)
            run.assert_not_called()
        self.assertFalse(dest.exists())
    def test_duplicate_manifest_key(self):
        self.reject_zip(lambda d:d.update({'MANIFEST.json':b'{"README.md":"x","README.md":"y"}'}))
    def test_payload_hash_mismatch(self):
        self.reject_zip(lambda d:d.update({'README.md':b'tampered'}))
    def test_unexpected_extra_file(self):
        self.reject_zip(lambda d:d.update({'private.env':b'synthetic'}))
    def test_missing_required_file(self):
        self.reject_zip(lambda d:d.pop('README.md'))
    def test_absolute_path(self):
        self.reject_zip(lambda d:d.update({'/tmp/abc-never-write':b'synthetic'}))
    def test_backslash_path(self):
        self.reject_zip(lambda d:d.update({'docs\\outside':b'synthetic'}))
    def test_source_link(self):
        self.reject_zip(lambda d:None,'README.md')
    def reject_read(self, op, args):
        db = self.root / 'synthetic.db'
        Coordinator(db).initialize('synthetic',True)
        command = [sys.executable,str(ROOT/'src/agent_browser_coordinator/coordinator.py'),'--db',str(db),op,'--args',args]
        out = self.root / 'dashboard.html'
        if op == 'dashboard':
            command += ['--output',str(out)]
        r = subprocess.run(command,capture_output=True,text=True,timeout=15,env=verify_install.minimal_environment())
        self.assertEqual(r.returncode,2)
        self.assertFalse(json.loads(r.stdout)['ok'])
        self.assertFalse(out.exists())
    def test_status_extra_argument(self):
        self.reject_read('status','{"extra":true}')
    def test_dashboard_extra_argument(self):
        self.reject_read('dashboard','{"extra":true}')
    def test_read_exponent_overflow(self):
        self.reject_read('status','{"n":1e999}')
    def test_read_nested_exponent_overflow(self):
        self.reject_read('status','{"n":{"x":[-1e999]}}')
    def test_duplicate_wheel_version(self):
        wheel = self.root / ('agent_browser_coordinator-'+VERSION+'-py3-none-any.whl')
        with zipfile.ZipFile(wheel,'w') as z:
            z.writestr('agent_browser_coordinator-'+VERSION+'.dist-info/METADATA','Name: agent-browser-coordinator\nVersion: '+VERSION+'\nVersion: 0.0.0\n')
        with patch.object(verify_install.subprocess,'run') as run:
            with self.assertRaises(ValueError):
                verify_install.verify(wheel,hashlib.sha256(wheel.read_bytes()).hexdigest())
            run.assert_not_called()
