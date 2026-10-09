import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coordinator import Coordinator,Conflict
class ManualReconcile(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.now=[1000.];self.c=Coordinator(Path(self.t.name)/'mock.db',lambda:self.now[0]);self.c.initialize('mock',True);self.n=0
  self.token=self.call('acquire',lease=10)['owner']['token'];self.call('begin',token=self.token,action='unknown-write');self.call('freeze','coordinator-operator');self.now[0]=1100.;self.user_at=1090.
  s=self.c.status();self.permit=self.call('diagnose-authorize','coordinator-operator',expected_revision=s['revision'],expected_token=self.token,expected_action='unknown-write',writer_paused=True,read_scope='new-tab-recent-posts')['diagnostic']['id'];self.call('diagnose-begin',token=self.token,permit=self.permit,read_scope='new-tab-recent-posts')
 def tearDown(self):self.t.cleanup()
 def call(self,op,actor='publisher',**kw):self.n+=1;return self.c.execute(op,f'r{self.n}',actor,**kw)
 def args(self):return dict(expected_revision=self.c.status()['revision'],expected_token=self.token,expected_action='unknown-write',writer_paused=True,no_known_running_invocations=True,user_completed=True,result_verified=True,user_ref='user-message',user_at=self.user_at,observation=self.permit,result_ref='verified-receipt')
 def finish_read(self):self.call('diagnose-end',token=self.token,permit=self.permit,read_completed=True)
 def test_observation_inflight_cannot_reconcile(self):
  with self.assertRaises(Conflict):self.call('manual-reconcile','coordinator-operator',**self.args())
 def test_manual_resolution_preserves_unknown_not_fake_end(self):
  self.finish_read();self.call('manual-reconcile','coordinator-operator',**self.args());s=self.c.status();self.assertIsNone(s['active']);self.assertIsNone(s['owner']);self.assertFalse(s['frozen']);self.assertEqual(s['unknown_action_outcomes'][0]['outcome'],'unknown');self.assertEqual(s['manual_reconciliations'][0]['resolution'],'manual_verified')
  with self.assertRaises(Conflict):self.call('end',token=self.token,action='unknown-write')
 def test_actor_and_fresh_evidence_required(self):
  self.finish_read()
  with self.assertRaises(Conflict):self.call('manual-reconcile','publisher',**self.args())
  with self.assertRaises(Conflict):self.call('manual-reconcile','coordinator-operator',**dict(self.args(),user_at=1101.))
  with self.assertRaises(Conflict):self.call('manual-reconcile','coordinator-operator',**dict(self.args(),result_verified=False))
 def test_replay_does_not_repeat_resolution(self):
  self.finish_read();args=self.args();a=self.c.execute('manual-reconcile','fixed','coordinator-operator',**args);b=self.c.execute('manual-reconcile','fixed','coordinator-operator',**args);self.assertFalse(a['replay']);self.assertTrue(b['replay']);self.assertEqual(len(self.c.status()['manual_reconciliations']),1)
if __name__=='__main__':unittest.main(verbosity=2)
