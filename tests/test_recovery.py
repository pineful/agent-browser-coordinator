import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
from agent_browser_coordinator.coordinator import Coordinator,Conflict
from scripts.verify_backup import restore
class RecoveryTests(unittest.TestCase):
 def test_missing_db_never_implies_idle(self):
  import sqlite3
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'missing.db'
   with self.assertRaises(sqlite3.Error):Coordinator(p).status()
   self.assertFalse(p.exists())
 def test_new_epoch_rejects_old_owner_token(self):
  with tempfile.TemporaryDirectory() as d:
   old=Coordinator(Path(d)/'old.db');old.initialize('mock',True);t=old.execute('acquire','a1','worker')['owner']['token']
   # Only a mock: all old calls drained and workers explicitly stopped before init.
   new=Coordinator(Path(d)/'new.db');new.initialize('mock',True);r=new.execute('acquire','a2','worker')
   self.assertNotEqual(t,r['owner']['token'])
   with self.assertRaises(Conflict):new.execute('begin','b1','worker',token=t,action='stale')
   self.assertFalse(new.status()['inventory_complete'])
 def test_wrong_archive_hash_stops_before_extraction(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.zip';p.write_bytes(b'not-a-backup');dest=Path(d)/'new'
   with self.assertRaises(ValueError):restore(p,'0'*64,dest)
   self.assertFalse(dest.exists())
 def test_existing_destination_never_overwritten(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.zip';p.write_bytes(b'content');dest=Path(d)/'live';dest.mkdir();marker=dest/'live.db';marker.write_text('preserve')
   with self.assertRaises(ValueError):restore(p,hashlib.sha256(p.read_bytes()).hexdigest(),dest)
   self.assertEqual(marker.read_text(),'preserve')
 def test_path_traversal_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('../bad','bad')
   with self.assertRaises(ValueError):restore(p,hashlib.sha256(p.read_bytes()).hexdigest(),Path(d)/'new')
   self.assertFalse((Path(d)/'bad').exists())
 def test_duplicate_archive_paths_rejected(self):
  import warnings
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.zip'
   with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    with zipfile.ZipFile(p,'w') as z:
     z.writestr('README.md','one');z.writestr('README.md','two')
   with self.assertRaises(ValueError):restore(p,hashlib.sha256(p.read_bytes()).hexdigest(),Path(d)/'new')
 def test_symlink_rejected(self):
  import stat
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.zip'
   info=zipfile.ZipInfo('README.md');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
   with zipfile.ZipFile(p,'w') as z:z.writestr(info,'/outside')
   with self.assertRaises(ValueError):restore(p,hashlib.sha256(p.read_bytes()).hexdigest(),Path(d)/'new')
 def test_incomplete_manifest_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('MANIFEST.json','{}')
   with self.assertRaises(ValueError):restore(p,hashlib.sha256(p.read_bytes()).hexdigest(),Path(d)/'new')
if __name__=='__main__':unittest.main()
