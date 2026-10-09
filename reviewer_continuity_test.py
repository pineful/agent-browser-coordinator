"""Independent v0.3 checks. Only temporary fixture DBs; no live UI or runtime access."""
import concurrent.futures
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import coordinator as mod
from coordinator import Coordinator, Conflict, MAX_CONTINUOUS_HOLD, MAX_QUEUE_WAIT, REJECTION_HISTORY

class ContinuityReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='review-v03-')
        self.path=Path(self.tmp.name)/'fixture.db';self.now=10000.;self.seq=0
        self.co=Coordinator(self.path,clock=lambda:self.now)
        self.co.initialize('isolated-review',confirmed_idle=True)
    def tearDown(self):self.tmp.cleanup()
    def call(self,op,actor='a',**kw):
        self.seq+=1;return self.co.execute(op,f'request-{self.seq}',actor,**kw)
    def take(self,actor='a',priority=10,lease=60):
        return self.call('acquire',actor,priority=priority,lease=lease)['owner']
    def raw(self):
        with sqlite3.connect(self.path) as c:
            return c.execute('SELECT body FROM state').fetchone()[0]
    def cycle(self,t,action,actor='a'):
        self.call('begin',actor,token=t,action=action)
        self.call('end',actor,token=t,action=action)
    def test_long_call_completion_renews_only_after_matching_end(self):
        a=self.take();self.call('begin',token=a['token'],action='long')
        self.now+=100;self.call('acquire','b',priority=0)
        self.assertTrue(self.co.status()['expired'])
        with self.assertRaises(Conflict):self.call('end','b',token=a['token'],action='long')
        with self.assertRaises(Conflict):self.call('end',token=a['token'],action='wrong')
        self.assertEqual(self.co.status()['active']['id'],'long')
        self.call('end',token=a['token'],action='long')
        self.assertEqual(self.co.status()['owner']['deadline'],self.now+60)
        self.assertEqual(self.co.status()['owner']['token'],a['token'])
    def test_expired_inflight_cannot_be_cleared_or_stolen(self):
        a=self.take();self.call('begin',token=a['token'],action='inflight')
        self.now+=MAX_CONTINUOUS_HOLD+100
        self.call('acquire','b',priority=100)
        for op,args in [('yield',dict(checkpoint='retained')),('release',{})]:
            with self.assertRaises(Conflict):self.call(op,token=a['token'],safe=True,no_pending_ui=True,**args)
        self.assertEqual(self.co.status()['owner']['token'],a['token'])
        self.assertEqual(self.co.status()['active']['id'],'inflight')
    def test_completion_after_hold_cap_can_end_but_cannot_renew(self):
        a=self.take();self.call('begin',token=a['token'],action='long-cap')
        deadline=self.co.status()['owner']['deadline']
        self.call('acquire','b',priority=0);self.now+=MAX_CONTINUOUS_HOLD+1
        self.call('end',token=a['token'],action='long-cap')
        self.assertIsNone(self.co.status()['active'])
        self.assertEqual(self.co.status()['owner']['deadline'],deadline)
        with self.assertRaises(Conflict):self.call('begin',token=a['token'],action='too-late')
        self.call('yield',token=a['token'],safe=True,no_pending_ui=True,checkpoint='boundary')
        self.assertEqual(self.co.status()['owner']['actor'],'b')
    def test_idle_ghost_heartbeat_does_not_bypass_two_minute_wait(self):
        a=self.take(priority=100,lease=3600);self.take('b',priority=0)
        self.now+=MAX_QUEUE_WAIT+1
        self.assertTrue(self.co.status()['yield_required'])
        with self.assertRaises(Conflict):self.call('heartbeat',token=a['token'])
    def test_heartbeat_cannot_extend_continuous_hold(self):
        a=self.take(lease=3600);limit=self.co.status()['hold_deadline']
        for delta in (60,300,600,1200,1799):
            self.now=10000+delta;self.call('heartbeat',token=a['token'])
            self.assertLessEqual(self.co.status()['owner']['deadline'],limit)
        self.now=limit
        with self.assertRaises(Conflict):self.call('heartbeat',token=a['token'])
        self.assertEqual(self.co.status()['owner']['token'],a['token'])
    def test_expired_return_requires_all_current_owner_acknowledgements(self):
        a=self.take();self.take('b');self.now+=61
        for args in ({'safe':True},{'no_pending_ui':True},{'safe':True,'no_pending_ui':'true'}):
            with self.assertRaises(Conflict):self.call('release',token=a['token'],**args)
        with self.assertRaises(Conflict):self.call('release','b',token=a['token'],safe=True,no_pending_ui=True)
        self.call('release',token=a['token'],safe=True,no_pending_ui=True)
        self.assertEqual(self.co.status()['owner']['actor'],'b')
    def test_explicit_yield_chooses_other_waiter_even_if_priority_lower(self):
        a=self.take(priority=100);self.take('b',priority=0)
        r=self.call('yield',token=a['token'],safe=True,checkpoint='saved-cp')
        self.assertEqual(r['owner']['actor'],'b')
        self.assertEqual(r['queue'][0]['actor'],'a')
    def test_overdue_fifo_prevents_high_priority_arrival_starvation(self):
        a=self.take(priority=100,lease=3600)
        self.take('oldest',priority=0);self.now+=1;self.take('older',priority=50)
        self.now+=MAX_QUEUE_WAIT+1;self.take('new-urgent',priority=100)
        r=self.call('yield',token=a['token'],safe=True,checkpoint='cp')
        self.assertEqual(r['owner']['actor'],'oldest')
        t=r['owner']['token'];self.call('release','oldest',token=t,safe=True)
        self.assertEqual(self.co.status()['owner']['actor'],'older')
    def test_newly_granted_overdue_waiter_gets_one_action_before_next_handoff(self):
        a=self.take(priority=100,lease=3600);self.take('b',priority=0)
        self.now+=1;self.take('c',priority=0);self.now+=MAX_QUEUE_WAIT+1
        r=self.call('yield',token=a['token'],safe=True,checkpoint='owner-cp')
        self.assertEqual(r['owner']['actor'],'b');t=r['owner']['token']
        self.cycle(t,'b-first-turn',actor='b')
        with self.assertRaises(Conflict):self.call('begin','b',token=t,action='b-second-turn')
        r=self.call('yield','b',token=t,safe=True,checkpoint='b-cp')
        self.assertEqual(r['owner']['actor'],'c')
    def test_completed_close_renews_after_lease_expiry(self):
        a=self.take();self.call('tab',token=a['token'],tab='own-tab',state='complete',unsaved=False)
        self.call('close-begin',token=a['token'],tab='own-tab',action='closing')
        self.now+=100;self.call('close-end',token=a['token'],action='closing',closed=True)
        self.assertEqual(self.co.status()['owner']['deadline'],self.now+60)
        self.assertNotIn('own-tab',self.co.status()['tabs'])
    def test_end_at_overdue_boundary_does_not_renew(self):
        a=self.take();self.call('begin',token=a['token'],action='waiting')
        self.take('b',priority=0);self.now+=MAX_QUEUE_WAIT
        before=self.co.status()['owner']['deadline'];self.call('end',token=a['token'],action='waiting')
        self.assertEqual(self.co.status()['owner']['deadline'],before)
        self.assertTrue(self.co.status()['yield_required'])
    def test_replayed_progress_does_not_extend_deadline(self):
        a=self.take();r=self.co.execute('begin','stable-begin','a',token=a['token'],action='one')
        self.now+=30;r2=self.co.execute('begin','stable-begin','a',token=a['token'],action='one')
        self.assertTrue(r2['replay']);self.assertEqual(self.co.status()['owner']['deadline'],r['owner']['deadline'])
    def test_concurrent_action_permits_keep_one_active_action(self):
        a=self.take(lease=3600)
        def attempt(n):
            try:
                c=Coordinator(self.path,clock=lambda:self.now)
                c.execute('begin',f'concurrent-{n}','a',token=a['token'],action=f'action-{n}')
                return True
            except Conflict:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            winners=list(pool.map(attempt,range(40)))
        self.assertEqual(sum(winners),1)
        self.assertEqual(self.co.status()['owner']['action_count'],1)
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM rejections').fetchone()[0],39)
    def test_audit_failure_cannot_turn_rejection_into_success_or_mutate_owner(self):
        a=self.take();self.now+=61;before=self.raw();real_connect=sqlite3.connect
        def connect(*args,**kwargs):
            if kwargs.get('timeout')==1:raise sqlite3.OperationalError('fixture audit unavailable')
            return real_connect(*args,**kwargs)
        with patch.object(mod.sqlite3,'connect',side_effect=connect):
            with self.assertRaises(Conflict) as caught:self.call('begin',token=a['token'],action='expired')
        self.assertFalse(caught.exception.audit_recorded)
        self.assertEqual(caught.exception.code,'LEASE_EXPIRED');self.assertEqual(self.raw(),before)
    def test_audit_is_bounded_and_omits_failed_payload(self):
        with sqlite3.connect(self.path) as c:
            c.executemany('INSERT INTO rejections(at,op,actor,code) VALUES(?,?,?,?)',[(self.now,'begin','fixture','COORDINATOR_REJECTED')]*REJECTION_HISTORY)
        a=self.take();self.now+=61
        with self.assertRaises(Conflict):self.call('begin',token=a['token'],action='private-sentinel',extra='private-payload-sentinel')
        with sqlite3.connect(self.path) as c:
            rows=c.execute('SELECT * FROM rejections').fetchall()
        self.assertEqual(len(rows),REJECTION_HISTORY)
        encoded=json.dumps(rows)
        self.assertNotIn('private-sentinel',encoded);self.assertNotIn('private-payload-sentinel',encoded);self.assertNotIn(a['token'],encoded)
    def test_malformed_request_rolls_back_even_if_not_audited(self):
        a=self.take();self.now+=1;before=self.raw()
        with self.assertRaises(KeyError):self.call('begin',token=a['token'])
        self.assertEqual(self.raw(),before)
    def test_auxiliary_absence_recovers_original_grant_origin(self):
        a=self.take(lease=3600);original=self.co.status()['hold_deadline']
        with sqlite3.connect(self.path) as c:c.execute('DROP TABLE grants');c.execute('DROP TABLE rejections')
        self.now+=500;self.call('heartbeat',token=a['token'])
        self.assertEqual(self.co.status()['hold_deadline'],original)
        with sqlite3.connect(self.path) as c:
            origin,limit=c.execute('SELECT granted_at,hold_deadline FROM grants WHERE token=?',(a['token'],)).fetchone()
        self.assertEqual(origin,10000);self.assertEqual(limit,10000+MAX_CONTINUOUS_HOLD)
    def test_future_grant_metadata_fails_closed(self):
        a=self.take(lease=3600)
        with sqlite3.connect(self.path) as c:
            c.execute('UPDATE grants SET granted_at=granted_at+500,hold_deadline=hold_deadline+500')
        before=self.raw()
        with self.assertRaises(Conflict):self.call('heartbeat',token=a['token'])
        self.assertEqual(self.raw(),before)
    def test_unknown_grant_origin_does_not_restart_hold_clock(self):
        a=self.take();self.now+=1
        with sqlite3.connect(self.path) as c:c.execute('DELETE FROM grants');c.execute('DELETE FROM requests')
        before=self.raw()
        with self.assertRaises(Conflict):self.call('heartbeat',token=a['token'])
        self.assertEqual(self.raw(),before)
        self.call('release',token=a['token'],safe=True)
        self.assertIsNone(self.co.status()['owner'])
    def test_rejection_audit_does_not_modify_unrecognized_sqlite_database(self):
        other=Path(self.tmp.name)/'unrecognized-fixture.db'
        with sqlite3.connect(other) as c:
            c.execute('CREATE TABLE unrelated(id INTEGER PRIMARY KEY, value TEXT)')
            c.execute('INSERT INTO unrelated(value) VALUES(?)',('public-fixture',))
        with sqlite3.connect(other) as c:
            before=c.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
        wrong=Coordinator(other,clock=lambda:self.now)
        with self.assertRaises(sqlite3.Error) as caught:wrong.execute('acquire','wrong-path','fixture')
        with sqlite3.connect(other) as c:
            after=c.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
        self.assertEqual(after,before)
        self.assertFalse(caught.exception.audit_recorded)
    def test_v1_state_wire_shape_remains_unchanged(self):
        a=self.take();self.cycle(a['token'],'bounded-progress')
        s=json.loads(self.raw())
        self.assertEqual(set(s),{'schema','resource','epoch','generation','owner','queue','active','frozen','tabs','shutdown','inventory_complete','last_time'})
        self.assertEqual(set(s['owner']),{'actor','priority','lease','enqueued','sequence','checkpoint','token','deadline','dispatch_priority','action_count'})
        self.assertEqual(s['schema'],1)

if __name__=='__main__':unittest.main(verbosity=2)
