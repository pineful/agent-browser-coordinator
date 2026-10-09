import sys,tempfile,unittest,json
from pathlib import Path
from agent_browser_coordinator.coordinator import Coordinator,Conflict
class Diagnostic(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.now=[1000.];self.c=Coordinator(Path(self.t.name)/'fixture.db',lambda:self.now[0]);self.c.initialize('mock',True);self.i=0
  self.token=self.call('acquire',lease=10)['owner']['token'];self.call('begin',token=self.token,action='uncertain-submit');self.now[0]+=2000;self.call('freeze','coordinator-operator')
 def tearDown(self):self.t.cleanup()
 def call(self,op,actor='publisher',**kw):self.i+=1;return self.c.execute(op,f'r{self.i}',actor,**kw)
 def authorize(self):
  s=self.c.status();return self.call('diagnose-authorize','coordinator-operator',expected_revision=s['revision'],expected_token=self.token,expected_action='uncertain-submit',writer_paused=True,read_scope='inventory-ax-screenshot')['diagnostic']['id']
 def test_single_owner_read_preserves_original_and_unknown_outcome(self):
  before=self.c.status();permit=self.authorize();r=self.call('diagnose-begin',token=self.token,permit=permit,read_scope='inventory-ax-screenshot');self.assertFalse(r['replay'])
  self.call('diagnose-end',token=self.token,permit=permit,read_completed=True);after=self.c.status()
  for k in ['owner','active','frozen','epoch','generation','tabs']:self.assertEqual(before[k],after[k])
  self.assertEqual(after['unknown_action_outcomes'][0]['outcome'],'unknown')
  with self.assertRaises(Conflict):self.call('diagnose-begin',token=self.token,permit=permit,read_scope='inventory-ax-screenshot')
 def test_other_actor_and_other_scope_denied(self):
  p=self.authorize()
  with self.assertRaises(Conflict):self.call('diagnose-begin','other',token=self.token,permit=p,read_scope='inventory-ax-screenshot')
  with self.assertRaises(Conflict):self.call('diagnose-begin',token=self.token,permit=p,read_scope='click')
 def test_no_write_or_fake_end_unlocked(self):
  p=self.authorize();self.call('diagnose-begin',token=self.token,permit=p,read_scope='inventory-ax-screenshot')
  for op,kw in [('begin',{'action':'another'}),('release',{'safe':True,'no_pending_ui':True}),('end',{'action':'uncertain-submit'})]:
   with self.assertRaises(Conflict):self.call(op,token=self.token,**kw)
  s=self.c.status()
  with self.assertRaises(Conflict):self.call('recover','coordinator-operator',expected_revision=s['revision'],expected_token=self.token,verified_idle=True,old_worker_quiescent=True,evidence='test',expected_shutdown_token=None)
 def test_operator_revision_token_and_pause_required(self):
  s=self.c.status();args=dict(expected_revision=s['revision'],expected_token=self.token,expected_action='uncertain-submit',writer_paused=True,read_scope='inventory-ax-screenshot')
  with self.assertRaises(Conflict):self.call('diagnose-authorize','publisher',**args)
  with self.assertRaises(Conflict):self.call('diagnose-authorize','coordinator-operator',**dict(args,writer_paused=False))
  with self.assertRaises(Conflict):self.call('diagnose-authorize','coordinator-operator',**dict(args,expected_revision=0))
 def test_failed_read_keeps_original_unknown(self):
  p=self.authorize();self.call('diagnose-begin',token=self.token,permit=p,read_scope='inventory-ax-screenshot');self.call('diagnose-end',token=self.token,permit=p,read_completed=False)
  s=self.c.status();self.assertEqual(s['active']['id'],'uncertain-submit');self.assertTrue(s['frozen']);self.assertEqual(s['diagnostics'][0]['status'],'read_failed')
 def test_expired_unstarted_permit_can_be_reauthorized_by_operator(self):
  old=self.authorize();self.now[0]+=121
  with self.assertRaises(Conflict):self.call('diagnose-begin',token=self.token,permit=old,read_scope='inventory-ax-screenshot')
  new=self.authorize();self.assertNotEqual(old,new)
 def test_replayed_authorize_or_begin_not_new_read_permit(self):
  p=self.authorize();r=self.c.execute('diagnose-begin','same-read','publisher',token=self.token,permit=p,read_scope='inventory-ax-screenshot');again=self.c.execute('diagnose-begin','same-read','publisher',token=self.token,permit=p,read_scope='inventory-ax-screenshot')
  self.assertFalse(r['replay']);self.assertTrue(again['replay'])
 def test_operator_can_authorize_separate_recent_posts_tab_scope(self):
  s=self.c.status();r=self.call('diagnose-authorize','coordinator-operator',expected_revision=s['revision'],expected_token=self.token,expected_action='uncertain-submit',writer_paused=True,read_scope='new-tab-recent-posts');permit=r['diagnostic']['id']
  self.assertEqual(r['diagnostic']['scope'],'new-tab-recent-posts')
  with self.assertRaises(Conflict):self.call('diagnose-begin',token=self.token,permit=permit,read_scope='inventory-ax-screenshot')
  self.call('diagnose-begin',token=self.token,permit=permit,read_scope='new-tab-recent-posts');self.call('diagnose-end',token=self.token,permit=permit,read_completed=True)
  after=self.c.status();self.assertTrue(after['frozen']);self.assertEqual(after['active'],s['active']);self.assertEqual(after['owner'],s['owner'])
 def test_completed_permit_does_not_authorize_later_observation(self):
  p=self.authorize();self.call('diagnose-begin',token=self.token,permit=p,read_scope='inventory-ax-screenshot');self.call('diagnose-end',token=self.token,permit=p,read_completed=True)
  with self.assertRaises(Conflict):self.call('diagnose-end',token=self.token,permit=p,read_completed=True)
if __name__=='__main__':unittest.main(verbosity=2)
