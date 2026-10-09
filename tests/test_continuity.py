import concurrent.futures,json,sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coordinator import Coordinator,Conflict,MAX_CONTINUOUS_HOLD,MAX_QUEUE_WAIT

class Continuity(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'mock.db';self.now=[1000.];self.c=Coordinator(self.path,lambda:self.now[0]);self.c.initialize('mock',True);self.i=0
 def tearDown(self):self.tmp.cleanup()
 def call(self,op,actor='a',**kw):self.i+=1;return self.c.execute(op,f'r{self.i}',actor,**kw)
 def take(self,actor='a',priority=10,lease=60):return self.call('acquire',actor,priority=priority,lease=lease)['owner']['token']
 def cycle(self,t,action):self.call('begin',token=t,action=action);self.call('end',token=t,action=action)
 def test_healthy_progress_renews_without_manual_heartbeat(self):
  t=self.take()
  for n in range(20):
   self.now[0]+=40;self.cycle(t,f'work-{n}')
   self.assertGreater(self.c.status()['owner']['deadline'],self.now[0])
  self.assertEqual(self.c.status()['owner']['token'],t)
 def test_long_inflight_not_stolen_and_matching_end_can_renew(self):
  t=self.take();self.call('begin',token=t,action='slow');self.now[0]+=200
  self.call('acquire','b',priority=0);s=self.c.status();self.assertTrue(s['expired']);self.assertEqual(s['owner']['token'],t)
  self.call('end',token=t,action='slow');self.assertFalse(self.c.status()['expired']);self.assertEqual(self.c.status()['owner']['token'],t)
 def test_no_renew_when_waiter_due(self):
  t=self.take();self.call('begin',token=t,action='slow');self.call('acquire','b',priority=0);self.now[0]+=MAX_QUEUE_WAIT+1
  self.call('end',token=t,action='slow');self.assertTrue(self.c.status()['expired'])
  self.call('yield',token=t,safe=True,no_pending_ui=True,checkpoint='safe');self.assertEqual(self.c.status()['owner']['actor'],'b')
 def test_expired_return_requires_current_owner_no_pending_ack(self):
  t=self.take();self.now[0]+=61;self.call('acquire','b')
  with self.assertRaises(Conflict):self.call('release',token=t,safe=True)
  with self.assertRaises(Conflict):self.call('release','b',token=t,safe=True,no_pending_ui=True)
  self.call('release',token=t,safe=True,no_pending_ui=True);self.assertEqual(self.c.status()['owner']['actor'],'b')
 def test_unknown_inflight_cannot_be_voluntarily_cleared(self):
  t=self.take();self.call('begin',token=t,action='unknown');self.now[0]+=61
  with self.assertRaises(Conflict):self.call('release',token=t,safe=True,no_pending_ui=True)
  self.assertEqual(self.c.status()['active']['id'],'unknown')
 def test_progress_and_heartbeats_cannot_exceed_max_hold(self):
  t=self.take(lease=3600);limit=self.c.status()['hold_deadline']
  self.now[0]+=MAX_CONTINUOUS_HOLD-10;self.cycle(t,'late');self.call('heartbeat',token=t)
  self.assertEqual(self.c.status()['owner']['deadline'],limit)
  self.now[0]=limit
  with self.assertRaises(Conflict):self.call('begin',token=t,action='over')
  with self.assertRaises(Conflict):self.call('heartbeat',token=t)
  self.call('yield',token=t,safe=True,no_pending_ui=True,checkpoint='boundary');self.assertNotEqual(self.c.status()['owner']['token'],t)
 def test_priority_waiter_blocks_renewal_and_next_action(self):
  t=self.take();self.cycle(t,'first');before=self.c.status()['owner']['deadline'];self.call('acquire','b',priority=100);self.now[0]+=1
  with self.assertRaises(Conflict):self.call('heartbeat',token=t)
  with self.assertRaises(Conflict):self.call('begin',token=t,action='again')
  self.assertEqual(self.c.status()['owner']['deadline'],before)
 def test_max_wait_protects_low_priority(self):
  t=self.take(priority=100,lease=3600);self.cycle(t,'first');self.call('acquire','b',priority=0);self.now[0]+=MAX_QUEUE_WAIT+1
  self.call('acquire','urgent',priority=100)
  with self.assertRaises(Conflict):self.call('begin',token=t,action='again')
  self.call('yield',token=t,safe=True,checkpoint='cp');self.assertEqual(self.c.status()['owner']['actor'],'b')
  b=self.c.status()['owner']['token'];self.call('begin','b',token=b,action='fair-first');self.call('end','b',token=b,action='fair-first')
 def test_explicit_yield_does_not_reselect_self_if_waiter_exists(self):
  t=self.take(priority=100);self.call('acquire','b',priority=0);self.call('yield',token=t,safe=True,checkpoint='cp')
  self.assertEqual(self.c.status()['owner']['actor'],'b')
 def test_rejections_record_only_sanitized_codes(self):
  t=self.take();self.now[0]+=61
  with self.assertRaises(Conflict):self.call('begin',token=t,action='private-action-label')
  errors=self.c.status()['recent_rejections'];self.assertEqual(errors[0]['code'],'LEASE_EXPIRED');self.assertNotIn('private-action-label',json.dumps(errors));self.assertNotIn(t,json.dumps(errors))
 def test_old_v02_auxiliary_absence_is_compatible(self):
  t=self.take()
  with sqlite3.connect(self.path) as c:c.execute('DROP TABLE grants');c.execute('DROP TABLE rejections')
  old_deadline=self.now[0]+MAX_CONTINUOUS_HOLD
  self.assertEqual(self.c.status()['hold_deadline'],old_deadline)
  self.now[0]+=10;self.cycle(t,'migration');self.assertEqual(self.c.status()['hold_deadline'],old_deadline)
 def test_frozen_completion_does_not_renew(self):
  t=self.take();self.call('begin',token=t,action='slow');deadline=self.c.status()['owner']['deadline'];self.call('freeze','operator');self.now[0]+=100
  self.call('end',token=t,action='slow');self.assertEqual(self.c.status()['owner']['deadline'],deadline)
 def test_old_end_and_replayed_begin_cannot_extend_hold(self):
  t=self.take();r=self.c.execute('begin','stable','a',token=t,action='once');self.now[0]+=20
  replay=self.c.execute('begin','stable','a',token=t,action='once');self.assertTrue(replay['replay']);self.assertEqual(replay['owner']['deadline'],r['owner']['deadline'])
  self.call('end',token=t,action='once');deadline=self.c.status()['owner']['deadline'];self.now[0]+=20
  with self.assertRaises(Conflict):self.call('end',token=t,action='once')
  self.assertEqual(self.c.status()['owner']['deadline'],deadline)
 def test_concurrent_requests_still_single_owner(self):
  def req(n):return Coordinator(self.path,lambda:self.now[0]).execute('acquire',f'parallel{n}',f'p{n}')
  with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:list(pool.map(req,range(30)))
  s=self.c.status();self.assertEqual(len(s['queue']),29);self.assertIsNotNone(s['owner'])
if __name__=='__main__':unittest.main(verbosity=2)
