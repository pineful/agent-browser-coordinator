import math
import tempfile
import unittest
from pathlib import Path

from agent_browser_coordinator.coordinator import Coordinator, Conflict
from agent_browser_coordinator.work_policy import classify_work
from agent_browser_coordinator.guard import run_guarded


class TimeSlicePolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1000.0]
        self.c = Coordinator(Path(self.tmp.name) / 'synthetic.db', lambda: self.now[0])
        self.c.initialize('synthetic-ui', True, time_slice_seconds=60)
        self.n = 0

    def tearDown(self): self.tmp.cleanup()

    def call(self, op, actor='a', **kw):
        self.n += 1
        return self.c.execute(op, f'request-{self.n}', actor, **kw)

    def test_waiter_triggers_next_boundary_without_interrupting_active_call(self):
        token = self.call('acquire', priority=10, lease=300)['owner']['token']
        self.call('begin', token=token, action='long')
        self.call('acquire', 'b', priority=0)
        self.now[0] += 61
        self.assertEqual(self.c.status()['active']['id'], 'long')
        self.assertEqual(self.c.status()['owner']['actor'], 'a')
        self.call('end', token=token, action='long')
        with self.assertRaises(Conflict): self.call('begin', token=token, action='again')
        self.call('yield', token=token, safe=True, checkpoint='saved')
        self.assertEqual(self.c.status()['owner']['actor'], 'b')

    def test_cancelled_waiter_and_empty_queue_do_not_force_rotation(self):
        token = self.call('acquire', priority=10, lease=300)['owner']['token']
        self.call('begin', token=token, action='first')
        self.call('end', token=token, action='first')
        self.call('acquire', 'b', priority=0)
        self.call('cancel', 'b')
        self.now[0] += 90
        self.call('begin', token=token, action='second')
        self.call('end', token=token, action='second')

    def test_stale_token_fails_after_yield_and_reacquisition(self):
        old = self.call('acquire', priority=10, lease=300)['owner']['token']
        self.call('acquire', 'b', priority=0)
        self.call('yield', token=old, safe=True, checkpoint='saved')
        b = self.c.status()['owner']['token']
        self.call('release', 'b', token=b, safe=True)
        new = self.c.status()['owner']['token']
        self.assertNotEqual(old, new)
        with self.assertRaises(Conflict): self.call('begin', token=old, action='stale')
        self.call('begin', token=new, action='fresh')
        self.call('end', token=new, action='fresh')

    def test_keep_alive_is_not_progress(self):
        token = self.call('acquire', lease=60)['owner']['token']
        deadline = self.c.status()['owner']['deadline']
        self.now[0] += 20
        self.call('heartbeat', token=token)
        status = self.c.status()
        self.assertEqual(status['last_keep_alive_at'], self.now[0])
        self.assertEqual(status['owner']['deadline'], deadline)
        self.now[0] = deadline
        with self.assertRaises(Conflict): self.call('begin', token=token, action='late')

    def test_bad_time_slice_rejected(self):
        for value in (True, 0, 29, 1801, 60.0, math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(Conflict):
                Coordinator(Path(self.tmp.name) / 'new.db').initialize('synthetic', True, value)

    def test_work_classification_fails_closed(self):
        for kind in ('unknown', 'shared-screen', 'keyboard', 'native-file-chooser', 'modal', 'tab-api'):
            self.assertEqual(classify_work(kind)['mode'], 'exclusive-ui')
        self.assertEqual(classify_work('file-analysis')['mode'], 'outside-ui')
        self.assertEqual(classify_work('server-generation-wait')['mode'], 'outside-ui')
        claim = dict(adapter='adapter-1', evidence='isolation-test-1', verified=True,
                     isolated_sessions=True, isolated_input=True, isolated_focus=True,
                     no_shared_dialogs=True)
        self.assertEqual(classify_work('tab-api', capability=claim)['mode'], 'parallel-candidate')
        for key in ('verified', 'isolated_sessions', 'isolated_input', 'isolated_focus', 'no_shared_dialogs'):
            bad = dict(claim, **{key: False})
            self.assertEqual(classify_work('tab-api', capability=bad)['mode'], 'exclusive-ui')
        self.assertEqual(classify_work('tab-api', capability={'tab_id': 'tab-1'})['mode'], 'exclusive-ui')

    def test_preparing_waiter_does_not_block_and_ready_handoff_is_signalled(self):
        token = self.call('acquire', priority=10, lease=300)['owner']['token']
        self.call('readiness', 'b', state='preparing')
        self.call('acquire', 'b', priority=0)
        self.now[0] += 130
        self.call('begin', token=token, action='continue')
        self.call('end', token=token, action='continue')
        self.assertIsNone(self.c.status()['next_ready_actor'])
        self.call('readiness', 'b', state='ready')
        status = self.c.status()
        self.assertEqual(status['next_ready_actor'], 'b')
        self.assertTrue(status['handoff_ready'])
        self.call('yield', token=token, safe=True, checkpoint='resume')
        self.assertEqual(self.c.status()['owner']['actor'], 'b')

    def test_idle_queue_waits_for_ready_actor_without_spawning_worker(self):
        self.call('readiness', 'a', state='preparing')
        self.call('acquire', 'a')
        self.assertIsNone(self.c.status()['owner'])
        self.assertIsNone(self.c.status()['next_ready_actor'])
        self.call('readiness', 'a', state='ready')
        self.assertEqual(self.c.status()['owner']['actor'], 'a')

    def test_resumed_owner_gets_observation_and_one_useful_call(self):
        a = self.call('acquire', priority=10, lease=300)['owner']['token']
        self.call('acquire', 'b', priority=0, lease=300)
        self.call('yield', token=a, safe=True, checkpoint='a-resume')
        b = self.c.status()['owner']['token']
        self.now[0] += 130
        self.call('yield', 'b', token=b, safe=True, checkpoint='b-resume')
        a2 = self.c.status()['owner']['token']
        self.now[0] += 61
        self.call('begin', token=a2, action='observe', kind='observation')
        self.call('end', token=a2, action='observe')
        self.call('begin', token=a2, action='useful', kind='work')
        self.call('end', token=a2, action='useful')
        with self.assertRaises(Conflict): self.call('begin', token=a2, action='third')
        self.call('yield', token=a2, safe=True, checkpoint='a-resume2')
        self.assertEqual(self.c.status()['owner']['actor'], 'b')

    def test_guard_refuses_replay_rejection_and_unknown_outcome(self):
        token = self.call('acquire', lease=300)['owner']['token']
        seen = []
        def adapter(): seen.append('called'); return True, 'observed'
        value = run_guarded(self.c, actor='a', token=token, action='view',
                            begin_request='guard-begin', end_request='guard-end', call=adapter)
        self.assertEqual(value, 'observed')
        self.assertEqual(seen, ['called'])
        with self.assertRaises(Conflict):
            run_guarded(self.c, actor='a', token=token, action='view',
                        begin_request='guard-begin', end_request='guard-end-2', call=adapter)
        self.assertEqual(seen, ['called'])
        self.call('acquire', 'b', priority=100)
        with self.assertRaises(Conflict):
            run_guarded(self.c, actor='a', token=token, action='rejected',
                        begin_request='guard-rejected', end_request='guard-rejected-end', call=adapter)
        self.assertEqual(seen, ['called'])

    def test_guard_keeps_uncertain_call_active(self):
        token = self.call('acquire', lease=300)['owner']['token']
        with self.assertRaises(Conflict):
            run_guarded(self.c, actor='a', token=token, action='unknown',
                        begin_request='uncertain-begin', end_request='uncertain-end',
                        call=lambda: (False, None))
        self.assertEqual(self.c.status()['active']['id'], 'unknown')

    def test_status_first_action_and_yield_signal_agree(self):
        token = self.call('acquire', priority=0, lease=300)['owner']['token']
        self.call('acquire', 'b', priority=100)
        status = self.c.status()
        self.assertTrue(status['first_action_available'])
        self.assertFalse(status['yield_required'])
        self.call('begin', token=token, action='first', kind='observation')
        self.call('end', token=token, action='first')
        self.assertTrue(self.c.status()['yield_required'])


if __name__ == '__main__': unittest.main()
