"""Independent safety review. Tests express required safety properties, not current behavior."""
import concurrent.futures
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from coordinator import Coordinator, Conflict

class Review(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'state.db')
        self.now = 10000.
        self.co = Coordinator(self.path, clock=lambda: self.now)
        self.co.initialize('test-browser', confirmed_idle=True)
        self.i = 0
    def tearDown(self): self.tmp.cleanup()
    def call(self, op, actor='a', **args):
        self.i += 1
        return self.co.execute(op, f'r{self.i}', actor, **args)
    def acquire(self, actor='a', **args):
        return self.call('acquire', actor, **args)['owner']
    def confirm_empty_inventory(self):
        a=self.acquire('inventory-operator')
        self.call('inventory','inventory-operator',token=a['token'],complete=True)
        self.call('release','inventory-operator',token=a['token'],safe=True)

    def corrupt(self, key, value):
        with sqlite3.connect(self.path) as c:
            s = json.loads(c.execute('SELECT body FROM state').fetchone()[0])
            s[key] = value
            c.execute('UPDATE state SET body=?', (json.dumps(s),))

    def test_initialization_requires_exact_idle_acknowledgement(self):
        for index, value in enumerate(('false', 1, [], {})):
            co=Coordinator(str(Path(self.tmp.name)/f'init-{index}.db'))
            with self.assertRaises(Conflict):
                co.initialize('browser',confirmed_idle=value)

    def test_recovery_rejects_stale_idle_snapshot_during_shutdown(self):
        # Operator observed idle (owner=None). Another actor then starts shutdown.
        self.confirm_empty_inventory()
        sh = self.call('shutdown-prepare', 'closer')['shutdown']
        self.call('shutdown-start', 'closer', token=sh['token'])
        self.acquire('b')
        with self.assertRaises(Conflict):
            self.call('recover', 'operator', expected_token=None,
                      verified_idle=True, evidence='old-idle-inspection')
        s = self.co.status()
        self.assertIsNone(s['owner'])
        self.assertEqual(s['shutdown']['phase'], 'running')

    def test_recovery_rejects_stale_idle_snapshot_after_begin(self):
        a = self.acquire()
        self.acquire('b', priority=0)
        self.call('begin', token=a['token'], action='live')
        with self.assertRaises(Conflict):
            self.call('recover', 'operator', expected_token=a['token'],
                      verified_idle=True, evidence='inspection-before-begin')
        self.assertEqual(self.co.status()['active']['id'], 'live')

    def test_frozen_blocks_new_tab_close(self):
        a = self.acquire()
        self.call('tab', token=a['token'], tab='tab-1', state='complete', unsaved=False)
        self.call('freeze', 'operator')
        with self.assertRaises(Conflict):
            self.call('close-begin', token=a['token'], tab='tab-1', action='close-1')

    def test_low_priority_waiter_eventually_requires_yield(self):
        a = self.acquire(priority=100, lease=3600)
        self.call('begin',token=a['token'],action='initial-action')
        self.call('end',token=a['token'],action='initial-action')
        self.acquire('b', priority=0)
        self.now += 121
        # v0.3: the 120-second wait bound forces a safe-boundary yield before the 1800-second hold cap.
        with self.assertRaises(Conflict):
            self.call('begin', token=a['token'], action='another-action')

    def test_aged_waiter_can_take_action_after_winning_grant(self):
        a = self.acquire(priority=100, lease=3600)
        self.acquire('b', priority=0)
        self.now += 121
        self.acquire('c', priority=100)
        result = self.call('yield', token=a['token'], safe=True, checkpoint='a-checkpoint')
        b = result['owner']
        self.assertEqual(b['actor'], 'b')
        result = self.call('begin', 'b', token=b['token'], action='b-first-action')
        self.assertEqual(result['active']['actor'], 'b')

    def test_semantic_corruption_fails_closed(self):
        self.acquire()
        self.corrupt('owner', [])
        with self.assertRaises((Conflict, ValueError, TypeError, KeyError, sqlite3.Error)):
            self.acquire('b')

    def test_tab_close_honors_preemption_at_next_boundary(self):
        a=self.acquire(priority=0)
        for tab in ('first-tab','second-tab'):
            self.call('tab',token=a['token'],tab=tab,state='complete',unsaved=False)
        self.call('close-begin',token=a['token'],tab='first-tab',action='close-first')
        self.call('close-end',token=a['token'],action='close-first',closed=True)
        self.acquire('b',priority=100)
        with self.assertRaises(Conflict):
            self.call('close-begin',token=a['token'],tab='second-tab',action='close-second')

    def test_old_end_cannot_end_reused_action_id(self):
        a = self.acquire()
        self.call('begin', token=a['token'], action='click')
        self.call('end', token=a['token'], action='click')
        # Either prevent action-id reuse, or require a per-action fencing token.
        try:
            self.call('begin', token=a['token'], action='click')
        except (Conflict, sqlite3.IntegrityError):
            return
        with self.assertRaises(Conflict):
            self.call('end', token=a['token'], action='click')

    def test_concurrent_acquires_keep_one_owner(self):
        def work(i):
            co=Coordinator(self.path, clock=lambda: self.now)
            co.execute('acquire', f'parallel-{i}', f'actor-{i}')
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(work, range(40)))
        s=self.co.status()
        self.assertIsNotNone(s['owner'])
        self.assertEqual(len(s['queue']),39)
        self.assertEqual(len({s['owner']['actor']} | {q['actor'] for q in s['queue']}),40)

    def test_expired_lease_never_grants_waiter(self):
        a=self.acquire(lease=10)
        self.acquire('b',priority=100)
        self.now += 100
        self.acquire('c',priority=100)
        self.assertEqual(self.co.status()['owner']['token'], a['token'])
        with self.assertRaises(Conflict):
            self.call('begin',token=a['token'],action='expired')

    def test_tabs_retained_on_yield_and_foreign_close_denied(self):
        a=self.acquire()
        self.call('tab',token=a['token'],tab='a-tab',state='working',unsaved=True)
        self.acquire('b',priority=100)
        result=self.call('yield',token=a['token'],safe=True,checkpoint='checkpoint-a')
        self.assertEqual(result['owner']['actor'],'b')
        s=self.co.status()
        self.assertEqual(s['tabs']['a-tab'],dict(actor='a',state='paused',unsaved=True))
        with self.assertRaises(Conflict):
            self.call('close-begin','b',token=s['owner']['token'],tab='a-tab',action='bad-close')
        with self.assertRaises(Conflict):
            self.call('begin',token=a['token'],action='stale')

    def test_restart_keeps_action_and_rollback_is_atomic(self):
        a=self.acquire()
        self.call('begin',token=a['token'],action='long-action')
        self.co=Coordinator(self.path,clock=lambda:self.now)
        self.assertEqual(self.co.status()['active']['id'],'long-action')
        before=self.co.status()
        with self.assertRaises(Conflict):
            self.call('release',token=a['token'],safe=True)
        after=self.co.status()
        prior_rejections=before.pop('recent_rejections')
        current_rejections=after.pop('recent_rejections')
        prior_counts=before.pop('rejection_counts_retained')
        current_counts=after.pop('rejection_counts_retained')
        expected_counts=dict(prior_counts)
        expected_counts['ACTION_IN_FLIGHT']=expected_counts.get('ACTION_IN_FLIGHT',0)+1
        self.assertEqual(current_counts,expected_counts)
        self.assertEqual(after,before)
        self.assertEqual(len(current_rejections),len(prior_rejections)+1)
        self.assertEqual(current_rejections[0]['code'],'ACTION_IN_FLIGHT')

    def test_process_crash_before_commit_preserves_state(self):
        self.acquire()
        before=self.co.status()
        code = """import os, sqlite3, sys
c=sqlite3.connect(sys.argv[1]); c.execute('BEGIN IMMEDIATE')
c.execute("UPDATE state SET body='corrupt-uncommitted-state'")
c.execute("INSERT INTO events(at,kind,actor) VALUES(10000,'uncommitted','crasher')")
os._exit(77)
"""
        result=subprocess.run([sys.executable,'-c',code,self.path], check=False)
        self.assertEqual(result.returncode,77)
        self.assertEqual(self.co.status(),before)

    def test_corrupt_closing_tab_ownership_fails_closed(self):
        a=self.acquire()
        self.call('tab',token=a['token'],tab='a-tab',state='complete',unsaved=False)
        self.call('close-begin',token=a['token'],tab='a-tab',action='close-a')
        tabs=self.co.status()['tabs']
        tabs['a-tab']['actor']='b'
        self.corrupt('tabs',tabs)
        with self.assertRaises((Conflict, ValueError, TypeError, sqlite3.Error)):
            self.call('close-end',token=a['token'],action='close-a',closed=True)

    def test_idempotent_state_change_occurs_once(self):
        first=self.co.execute('acquire','idem','a')
        replay=self.co.execute('acquire','idem','a')
        self.assertTrue(replay.pop('replay', True))
        first.pop('replay', None)
        self.assertEqual(replay,first)
        self.assertEqual(len(self.co.status()['events']),1)
        with self.assertRaises(Conflict):
            self.co.execute('acquire','idem','b')

    def test_status_state_and_revision_share_one_snapshot(self):
        self.acquire()
        writer = Coordinator(self.path, clock=lambda: self.now)
        original_connect = sqlite3.connect
        def quick_connect(*args, **kwargs):
            kwargs['timeout'] = 0.02
            return original_connect(*args, **kwargs)
        def race_clock():
            try:
                writer.execute('freeze', 'concurrent-freeze', 'operator')
            except sqlite3.OperationalError as exc:
                self.assertIn('locked', str(exc))
            return self.now
        reader = Coordinator(self.path, clock=race_clock)
        with patch('sqlite3.connect', side_effect=quick_connect):
            s = reader.status()
        self.assertEqual(s['frozen'], s['revision'] == 2)

    def test_recovery_rejects_changed_frozen_revision(self):
        a=self.acquire()
        snap=self.call('freeze','operator')
        self.acquire('b')
        with self.assertRaises(Conflict):
            self.call('recover','operator',expected_token=a['token'],
                      expected_revision=snap['revision'],expected_shutdown_token=None,
                      verified_idle=True,evidence='previous-inspection')

    def test_recovery_allows_frozen_exact_snapshot(self):
        a=self.acquire()
        self.acquire('b')
        self.call('freeze','operator')
        s=self.co.status()
        r=self.call('recover','operator',expected_token=a['token'],
                    expected_revision=s['revision'],expected_shutdown_token=None,
                    verified_idle=True,old_worker_quiescent=True,evidence='externally-verified-idle')
        self.assertEqual(r['owner']['actor'],'b')
        self.assertIsNone(r['active'])

    def test_unknown_inventory_blocks_shutdown(self):
        self.assertIn('unknown_tabs',self.co.status()['shutdown_blockers'])
        with self.assertRaises(Conflict):
            self.call('shutdown-prepare','closer')
        self.confirm_empty_inventory()
        self.assertNotIn('unknown_tabs',self.co.status()['shutdown_blockers'])
        self.call('shutdown-prepare','closer')

    def test_recovery_invalidates_precrash_inventory(self):
        self.confirm_empty_inventory()
        a=self.acquire()
        self.call('begin',token=a['token'],action='possibly-opened-new-tab')
        self.call('freeze','operator')
        s=self.co.status()
        self.call('recover','operator',expected_token=a['token'],
                  expected_revision=s['revision'],expected_shutdown_token=None,
                  verified_idle=True,old_worker_quiescent=True,evidence='crashed-worker-drained')
        self.assertFalse(self.co.status()['inventory_complete'])
        with self.assertRaises(Conflict):
            self.call('shutdown-prepare','closer')

    def test_shutdown_running_holds_enqueue_until_end(self):
        self.confirm_empty_inventory()
        sh=self.call('shutdown-prepare','closer')['shutdown']
        self.call('shutdown-start','closer',token=sh['token'])
        r=self.call('acquire','b')
        self.assertIsNone(r['owner'])
        self.assertEqual(r['shutdown']['phase'],'running')
        r=self.call('shutdown-end','closer',token=sh['token'],closed=True)
        self.assertEqual(r['owner']['actor'],'b')
        self.assertFalse(self.co.status()['inventory_complete'])

    def test_enqueue_before_shutdown_start_cancels_shutdown(self):
        self.confirm_empty_inventory()
        sh=self.call('shutdown-prepare','closer')['shutdown']
        self.acquire('b')
        r=self.call('shutdown-start','closer',token=sh['token'])
        self.assertIsNone(r['shutdown'])
        self.assertEqual(r['owner']['actor'],'b')

if __name__=='__main__': unittest.main(verbosity=2)
