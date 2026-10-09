import concurrent.futures, json, os, sqlite3, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coordinator import Coordinator, Conflict

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'s.db'; self.now=[1000.]; self.c=Coordinator(self.path,lambda:self.now[0]); self.c.initialize('mock',True); self.i=0
 def tearDown(self): self.tmp.cleanup()
 def do(self,op,actor='a',**kw):
  self.i+=1; return self.c.execute(op,str(self.i),actor,**kw)
 def acquire(self,actor='a',priority=0): return self.do('acquire',actor,priority=priority)['owner']['token']
 def test_concurrent_single_owner(self):
  def req(i): return Coordinator(self.path).execute('acquire',f'r{i}',f'a{i}')
  with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool: list(pool.map(req,range(40)))
  s=Coordinator(self.path).status(); self.assertEqual(len(s['queue']),39); self.assertIsNotNone(s['owner'])
 def test_preempt_safe_checkpoint_resume(self):
  t=self.acquire(); self.do('tab',token=t,tab='tab-a',state='working',unsaved=True)
  self.do('begin',token=t,action='click'); self.do('acquire','b',priority=100)
  with self.assertRaises(Conflict): self.do('yield',token=t,safe=True,checkpoint='cp-a')
  self.do('end',token=t,action='click')
  with self.assertRaises(Conflict): self.do('begin',token=t,action='second')
  self.do('yield',token=t,safe=True,checkpoint='cp-a'); s=self.c.status(); self.assertEqual(s['owner']['actor'],'b'); self.assertEqual(s['tabs']['tab-a']['state'],'paused')
  self.do('release','b',token=s['owner']['token'],safe=True); s=self.c.status(); self.assertEqual(s['owner']['actor'],'a'); self.assertEqual(s['owner']['checkpoint'],'cp-a'); self.assertNotEqual(t,s['owner']['token'])
  with self.assertRaises(Conflict): self.do('begin',token=t,action='stale')
 def test_aging(self):
  t=self.acquire(priority=100); self.do('acquire','b',priority=0); self.now[0]+=3010
  # Refresh lease cannot revive expired one; construct long initial lease separately.
  with self.assertRaises(Conflict): self.do('heartbeat',token=t)
  self.assertEqual(self.c.status()['owner']['actor'],'a')
 def test_wait_bound_preemption(self):
  t=self.do('acquire',priority=100,lease=3600)['owner']['token']; self.do('begin',token=t,action='first'); self.do('end',token=t,action='first'); self.do('acquire','b',priority=0)
  self.now[0]+=121
  with self.assertRaises(Conflict): self.do('begin',token=t,action='click')
  self.do('yield',token=t,safe=True,checkpoint='cp'); self.assertEqual(self.c.status()['owner']['actor'],'b')
 def test_expiry_fail_closed_recovery(self):
  t=self.acquire(); self.do('begin',token=t,action='slow'); self.now[0]+=200; self.do('acquire','b',priority=100)
  self.assertEqual(self.c.status()['owner']['actor'],'a')
  with self.assertRaises(Conflict): self.do('recover','operator',verified_idle=False,evidence='check',expected_token=t)
  with self.assertRaises(Conflict): self.do('release',token=t,safe=True)
  self.do('end',token=t,action='slow'); self.do('freeze','operator'); self.do('recover','operator',verified_idle=True,old_worker_quiescent=True,evidence='tool-complete',expected_token=t,expected_revision=self.c.status()['revision'])
  self.assertEqual(self.c.status()['owner']['actor'],'b')
 def test_idempotent_restart(self):
  r=self.c.execute('acquire','once','a'); c=Coordinator(self.path,lambda:self.now[0]); again=c.execute('acquire','once','a'); self.assertTrue(again['replay']); self.assertEqual(r['owner'],again['owner'])
  with self.assertRaises(Conflict): c.execute('acquire','once','b')
 def test_close_gate(self):
  t=self.acquire(); self.do('tab',token=t,tab='t1',state='complete',unsaved=True)
  with self.assertRaises(Conflict): self.do('close-begin',token=t,tab='t1',action='close')
  self.do('tab',token=t,tab='t1',state='complete',unsaved=False); self.do('close-begin',token=t,tab='t1',action='close')
  with self.assertRaises(Conflict): self.do('release',token=t,safe=True)
  self.do('close-end',token=t,action='close',closed=False); self.assertIn('t1',self.c.status()['tabs'])
  self.do('close-begin',token=t,tab='t1',action='close2'); self.do('close-end',token=t,action='close2',closed=True); self.assertFalse(self.c.status()['tabs'])
 def test_other_actor_tab_preserved(self):
  t=self.acquire(); self.do('tab',token=t,tab='t1',state='complete',unsaved=False); self.do('release',token=t,safe=True); u=self.acquire('b')
  with self.assertRaises(Conflict): self.do('close-begin','b',token=u,tab='t1',action='close')
 def test_shutdown_race(self):
  t=self.acquire(); self.do('inventory',token=t,complete=True); self.do('release',token=t,safe=True)
  r=self.do('shutdown-prepare','operator'); token=r['shutdown']['token']; self.do('acquire','b')
  self.assertIsNone(self.c.status()['owner']); self.do('shutdown-start','operator',token=token); self.assertIsNone(self.c.status()['shutdown']); self.assertEqual(self.c.status()['owner']['actor'],'b')
 def test_shutdown_inflight(self):
  t=self.acquire(); self.do('inventory',token=t,complete=True); self.do('release',token=t,safe=True)
  t=self.do('shutdown-prepare','operator')['shutdown']['token']; self.do('shutdown-start','operator',token=t); self.do('acquire','b'); self.assertIsNone(self.c.status()['owner'])
  self.do('shutdown-end','operator',token=t,closed=True); self.assertEqual(self.c.status()['owner']['actor'],'b')
 def test_shutdown_tabs_block(self):
  t=self.acquire(); self.do('tab',token=t,tab='unsaved',state='held',unsaved=True); self.do('release',token=t,safe=True)
  with self.assertRaises(Conflict): self.do('shutdown-prepare','operator')
 def test_freeze(self):
  t=self.acquire(); self.do('freeze','operator'); self.do('acquire','b'); self.do('release',token=t,safe=True); self.assertIsNone(self.c.status()['owner'])
 def test_clock_rollback(self):
  self.acquire(); self.now[0]-=1
  with self.assertRaises(Conflict): self.do('heartbeat',token=self.c.status()['owner']['token'])
 def test_missing_corrupt_no_recreate(self):
  other=Path(self.tmp.name)/'absent'
  with self.assertRaises(sqlite3.Error): Coordinator(other).status()
  self.assertFalse(other.exists()); self.path.write_bytes(b'bad')
  with self.assertRaises(sqlite3.Error): self.c.status()
 def test_transaction_rollback(self):
  self.do('freeze','op'); before=self.c.status()
  with self.assertRaises(KeyError): self.do('recover','op',verified_idle=True,old_worker_quiescent=True,expected_revision=before['revision'])
  self.assertEqual(before,self.c.status())
 def test_unknown_inventory_blocks_shutdown(self):
  with self.assertRaises(Conflict): self.do('shutdown-prepare','operator')
  self.assertIn('unknown_tabs',self.c.status()['shutdown_blockers'])
 def test_init_guard(self):
  with self.assertRaises(FileExistsError): self.c.initialize('mock',True)
 def test_no_secret_identifiers(self):
  with self.assertRaises(Conflict): self.do('acquire','name?secret=oops')
if __name__=='__main__': unittest.main(verbosity=2)
