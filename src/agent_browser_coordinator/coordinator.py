#!/usr/bin/env python3
"""Cooperative resource arbiter; never an OS/browser security boundary."""
import argparse, contextlib, html, json, math, os, re, sqlite3, stat, time, uuid
from pathlib import Path

VERSION = "0.3.5"
MAX_CONTINUOUS_HOLD = 1800
MAX_QUEUE_WAIT = 120
DEFAULT_TIME_SLICE = 180
REJECTION_HISTORY = 2000

class Conflict(Exception): pass

def label(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}', value):
        raise Conflict('Use an opaque identifier (1-120 safe characters), not private content')
    return value

def _reject_constant(value):
    raise ValueError('Non-finite JSON number rejected')

def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('Duplicate JSON key rejected')
        result[key]=value
    return result

def _finite_float(text):
    value=float(text)
    if not math.isfinite(value): raise ValueError('Non-finite JSON number rejected')
    return value

def strict_json(text):
    return json.loads(text,parse_constant=_reject_constant,parse_float=_finite_float,object_pairs_hook=_unique_object)

ARGUMENTS = {
    'acquire': {'priority','lease'}, 'heartbeat': {'token'}, 'readiness': {'state'},
    'begin': {'token','action','kind'}, 'end': {'token','action'},
    'inventory': {'token','complete'}, 'tab': {'token','tab','state','unsaved'},
    'close-begin': {'token','tab','action'}, 'close-end': {'token','action','closed'},
    'yield': {'token','safe','checkpoint','no_pending_ui'},
    'release': {'token','safe','checkpoint','no_pending_ui'}, 'cancel': set(),
    'freeze': set(),
    'recover': {'verified_idle','old_worker_quiescent','evidence','expected_revision','expected_token','expected_shutdown_token'},
    'shutdown-prepare': set(), 'shutdown-start': {'token'}, 'shutdown-end': {'token','closed'},
    'diagnose-authorize': {'expected_revision','expected_token','expected_action','writer_paused','read_scope'},
    'diagnose-begin': {'token','permit','read_scope'}, 'diagnose-end': {'token','permit','read_completed'},
    'manual-reconcile': {'expected_revision','expected_token','expected_action','writer_paused','no_known_running_invocations','user_completed','result_verified','user_at','observation','user_ref','result_ref'},
}
BOOL_ARGUMENTS = {'complete','unsaved','closed','safe','no_pending_ui','verified_idle','old_worker_quiescent','writer_paused','read_completed','no_known_running_invocations','user_completed','result_verified'}
LABEL_ARGUMENTS = {'token','action','tab','checkpoint','evidence','expected_token','expected_shutdown_token','expected_action','permit','observation','user_ref','result_ref'}

def validate_arguments(op,kw):
    if not isinstance(op,str) or op not in ARGUMENTS:
        raise Conflict('Unknown operation')
    if set(kw)-ARGUMENTS[op]: raise Conflict('Unexpected argument keys; no extra payload is stored')
    for key,value in kw.items():
        if key in BOOL_ARGUMENTS and type(value)!=bool: raise Conflict('Explicit boolean argument required')
        if key in LABEL_ARGUMENTS:
            if value is None and key in {'checkpoint','expected_token','expected_shutdown_token'}: continue
            label(value)
        if key=='expected_revision' and (type(value)!=int or value<0): raise Conflict('Revision must be a non-negative integer')
    try:
        if len(json.dumps(kw,allow_nan=False).encode('utf-8'))>16384: raise Conflict('Request payload too large')
    except (TypeError,ValueError) as error:
        raise Conflict('Invalid request value') from error

def write_dashboard(path,text):
    # A new file only: never clobber a DB, hard link, symlink, or prior output.
    target=Path(os.path.abspath(os.fspath(path)))
    for component in [target,*target.parents]:
        if component.is_symlink(): raise Conflict('Symlink output paths are not supported')
    if not target.parent.is_dir() or target.parent.stat().st_mode & 0o022:
        raise Conflict('Output parent must be an existing trusted directory without group/world write')
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        stream.write(text)

class Coordinator:
    def __init__(self, path, clock=time.time):
        self.path = os.path.abspath(os.fspath(path)); self.clock = clock

    def _now(self):
        now=self.clock()
        if type(now) not in (int,float) or not math.isfinite(now):
            raise Conflict('Clock must return a finite number')
        return now

    def _checked_db_path(self,require_exists=True):
        path=Path(self.path)
        for component in [path,*path.parents]:
            if component.is_symlink(): raise Conflict('Symlink database paths are not supported')
        if not path.parent.is_dir() or path.parent.stat().st_mode & 0o022:
            raise Conflict('Database parent must be an existing trusted directory without group/world write')
        if not path.exists():
            if require_exists: raise sqlite3.OperationalError('Missing database; explicit recovery required')
            return None
        info=path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise Conflict('Database must be a regular file without hard links')
        return (info.st_dev,info.st_ino)

    def _same_db(self,expected):
        if self._checked_db_path()!=expected:
            raise Conflict('Database identity changed; stop and inspect offline')

    def initialize(self, resource, confirmed_idle=False, time_slice_seconds=DEFAULT_TIME_SLICE):
        label(resource)
        if confirmed_idle is not True: raise Conflict('Initial activation requires externally verified idle resource')
        if type(time_slice_seconds)!=int or not 30<=time_slice_seconds<=1800:
            raise Conflict('time_slice_seconds must be an integer 30..1800 seconds')
        now=self._now();self._checked_db_path(require_exists=False)
        fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
        c=None
        try:
            info=os.fstat(fd);identity=(info.st_dev,info.st_ino)
            self._same_db(identity)
            c=sqlite3.connect(Path(self.path).as_uri()+'?mode=rw',uri=True)
            self._same_db(identity)
            with c:
                c.executescript('''
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
                CREATE TABLE requests(id TEXT PRIMARY KEY, args TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE actions(id TEXT PRIMARY KEY);
                CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, kind TEXT, actor TEXT);
                ''')
                s=dict(schema=1,resource=resource,epoch=uuid.uuid4().hex,generation=0,
                       owner=None,queue=[],active=None,frozen=False,tabs={},shutdown=None,inventory_complete=False,last_time=now)
                self._validate(s)
                c.execute('INSERT INTO state VALUES(1,?)',(json.dumps(s,allow_nan=False),))
                self._ensure_auxiliary(c)
                c.execute('UPDATE policy SET time_slice_seconds=? WHERE id=1',(time_slice_seconds,))
        finally:
            if c is not None:c.close()
            os.close(fd)
        return self.status()

    @contextlib.contextmanager
    def connection(self, readonly=False):
        # rw/ro mode intentionally never creates missing state.
        identity=self._checked_db_path()
        c = sqlite3.connect(Path(self.path).as_uri()+ ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=15)
        try:
            self._same_db(identity)
            if not readonly:
                c.execute('PRAGMA synchronous=FULL'); c.execute('BEGIN IMMEDIATE')
            else: c.execute('BEGIN')
            row = c.execute('SELECT body FROM state WHERE id=1').fetchone()
            if not row: raise Conflict('Missing state; manual recovery required')
            s = strict_json(row[0])
            self._validate(s)
            if not readonly: self._ensure_auxiliary(c)
            yield c, s
            if not readonly: c.commit()
        except BaseException:
            c.rollback(); raise
        finally: c.close()

    @staticmethod
    def _ensure_auxiliary(c):
        # Additive tables keep the v1 state/owner wire shape compatible.
        c.execute('CREATE TABLE IF NOT EXISTS grants(token TEXT PRIMARY KEY, granted_at REAL NOT NULL, hold_deadline REAL NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS rejections(seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, op TEXT, actor TEXT, code TEXT)')
        c.execute("CREATE TABLE IF NOT EXISTS diagnostics(id TEXT PRIMARY KEY, actor TEXT NOT NULL, token TEXT NOT NULL, original_action TEXT NOT NULL, created_at REAL NOT NULL, status TEXT NOT NULL, finished_at REAL, scope TEXT NOT NULL DEFAULT 'inventory-ax-screenshot')")
        if 'scope' not in {r[1] for r in c.execute('PRAGMA table_info(diagnostics)')}: c.execute("ALTER TABLE diagnostics ADD COLUMN scope TEXT NOT NULL DEFAULT 'inventory-ax-screenshot'")
        c.execute('CREATE TABLE IF NOT EXISTS uncertain_actions(action TEXT PRIMARY KEY, actor TEXT NOT NULL, recorded_at REAL NOT NULL, outcome TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS manual_reconciliations(action TEXT PRIMARY KEY, actor TEXT NOT NULL, at REAL NOT NULL, user_ref TEXT NOT NULL, user_at REAL NOT NULL, observation TEXT NOT NULL, result_ref TEXT NOT NULL, original_outcome TEXT NOT NULL, resolution TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS policy(id INTEGER PRIMARY KEY CHECK(id=1), time_slice_seconds INTEGER NOT NULL)')
        c.execute('INSERT OR IGNORE INTO policy VALUES(1,?)',(DEFAULT_TIME_SLICE,))
        c.execute('CREATE TABLE IF NOT EXISTS liveness(token TEXT PRIMARY KEY, seen_at REAL NOT NULL)')
        c.execute("CREATE TABLE IF NOT EXISTS work_readiness(actor TEXT PRIMARY KEY, state TEXT NOT NULL CHECK(state IN ('preparing','ready')), updated_at REAL NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS action_kinds(action TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('observation','work')))")
        c.execute('CREATE TABLE IF NOT EXISTS grant_service(token TEXT PRIMARY KEY, completed_work INTEGER NOT NULL)')

    @staticmethod
    def _ready_queue(c,s):
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_readiness'").fetchone(): return s['queue']
        states=dict(c.execute('SELECT actor,state FROM work_readiness'))
        if any(state not in ('preparing','ready') for state in states.values()): raise Conflict('Invalid readiness state; verified recovery required')
        return [q for q in s['queue'] if states.get(q['actor'],'ready')=='ready']

    @staticmethod
    def _time_slice(c):
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='policy'").fetchone(): return DEFAULT_TIME_SLICE
        row=c.execute('SELECT time_slice_seconds FROM policy WHERE id=1').fetchone()
        if not row or type(row[0])!=int or not 30<=row[0]<=1800: raise Conflict('Invalid time slice policy; verified recovery required')
        return row[0]

    @staticmethod
    def _error_code(error):
        msg=str(error)
        for prefix,code in [('Lease expired','LEASE_EXPIRED'),('Expired lease','EXPIRED_RETURN_ACK_REQUIRED'),('Maximum hold','MAX_HOLD_REACHED'),('Higher priority waiter','YIELD_REQUIRED'),('Time slice','YIELD_REQUIRED'),('Action in flight','ACTION_IN_FLIGHT'),('Coordinator frozen','FROZEN'),('Stale','STALE_TOKEN'),('State changed','RECOVERY_REVISION_CHANGED'),('Unknown hold','HOLD_ORIGIN_UNKNOWN')]:
            if msg.startswith(prefix): return code
        return 'COORDINATOR_REJECTED'

    def _audit_rejection(self, op, actor, code):
        # No payload, URL, exception text, or tool result is persisted here.
        operations={'acquire','heartbeat','readiness','begin','end','yield','release','cancel','freeze','recover','tab','inventory','close-begin','close-end','shutdown-prepare','shutdown-start','shutdown-end','diagnose-authorize','diagnose-begin','diagnose-end','manual-reconcile'}
        try:
            actor=label(actor)
        except Conflict: actor='invalid-actor'
        try:
            identity=self._checked_db_path(); now=self._now()
            c=sqlite3.connect(Path(self.path).as_uri()+'?mode=rw',uri=True,timeout=10)
            try:
                self._same_db(identity)
                c.execute('BEGIN IMMEDIATE')
                tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'state','requests','actions','events'}<=tables: raise Conflict('Not a coordinator database')
                row=c.execute('SELECT body FROM state WHERE id=1').fetchone()
                if not row: raise Conflict('Missing coordinator state')
                self._validate(strict_json(row[0]))
                self._ensure_auxiliary(c)
                c.execute('INSERT INTO rejections(at,op,actor,code) VALUES(?,?,?,?)',(now,op if isinstance(op,str) and op in operations else 'unknown',actor,code))
                c.execute('DELETE FROM rejections WHERE seq <= (SELECT COALESCE(MAX(seq),0)-? FROM rejections)',(REJECTION_HISTORY,))
                c.commit(); return True
            finally: c.close()
        except (Conflict,sqlite3.Error,OSError,ValueError,KeyError,TypeError): return False

    def _hold_deadline(self,c,o,create=True):
        present=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='grants'").fetchone()
        row=c.execute('SELECT granted_at,hold_deadline FROM grants WHERE token=?',(o['token'],)).fetchone() if present else None
        if row:
            if not all(type(x) in (int,float) and math.isfinite(x) for x in row) or row[1]-row[0]!=MAX_CONTINUOUS_HOLD or row[0]>json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0])['last_time']: raise Conflict('Invalid hold metadata; verified recovery required')
            return row[1]
        # Compatibility with grants made by v0.2; infer once from the first
        # committed response carrying this generation, never from current time.
        for (body,) in c.execute('SELECT result FROM requests ORDER BY rowid'):
            result=json.loads(body); previous=result.get('owner')
            if previous and previous.get('token')==o['token']:
                event=c.execute('SELECT at FROM events WHERE seq=?',(result['revision'],)).fetchone()
                if event:
                    deadline=event[0]+MAX_CONTINUOUS_HOLD
                    if create: c.execute('INSERT OR IGNORE INTO grants VALUES(?,?,?)',(o['token'],event[0],deadline))
                    return deadline
        raise Conflict('Unknown hold origin; voluntarily release or use verified recovery')

    def _should_yield(self,c,s,now,allow_first_action=False):
        o=s['owner']
        ready=self._ready_queue(c,s)
        # A resumed worker gets at most two calls to complete one useful work
        # action after a fresh observation. Work must be explicitly marked;
        # an observation alone does not consume the useful-service chance.
        service_table=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='grant_service'").fetchone()
        completed=c.execute('SELECT completed_work FROM grant_service WHERE token=?',(o['token'],)).fetchone() if o and service_table else None
        service_floor = bool(o and o['checkpoint'] and o['action_count'] < 2 and not (completed and completed[0]))
        return bool(o and not service_floor and (not allow_first_action or o['action_count']) and ready and
                    (any(now-q['enqueued']>=MAX_QUEUE_WAIT for q in ready) or
                     max(self._rank(q,now)[0] for q in ready)>o['dispatch_priority'] or
                     any(now-q['enqueued']>=self._time_slice(c) for q in ready)))

    def _allow_new_action(self,c,s,now,allow_first_action=False):
        if s['frozen']: raise Conflict('Coordinator frozen')
        if now>=self._hold_deadline(c,s['owner']): raise Conflict('Maximum hold reached: checkpoint and yield or release')
        if self._should_yield(c,s,now,allow_first_action): raise Conflict('Time slice or waiter priority requires checkpoint and yield')

    def _renew_for_progress(self,c,s,now):
        # Only explicit current-owner progress; never a timer or observer renewal.
        # A matched end may renew after a long, now-completed call, but not if
        # fairness, freeze, or the bounded continuous-hold budget requires handoff.
        limit=self._hold_deadline(c,s['owner'])
        if not s['frozen'] and now<limit and not self._should_yield(c,s,now):
            s['owner']['deadline']=min(now+s['owner']['lease'],limit)

    @staticmethod
    def _validate(s):
        def require(ok):
            if not ok: raise Conflict('Invalid state; fail closed and inspect offline')
        def number(v): return type(v) in (int,float) and math.isfinite(v)
        require(type(s)==dict and type(s.get('schema'))==int and s['schema']==1)
        require(set(s)=={'schema','resource','epoch','generation','owner','queue','active','frozen','tabs','shutdown','inventory_complete','last_time'})
        label(s['resource']); label(s['epoch'])
        require(type(s['generation'])==int and s['generation']>=0 and type(s['frozen'])==bool and number(s['last_time']))
        require(type(s['inventory_complete'])==bool)
        require(type(s['queue'])==list and type(s['tabs'])==dict)
        actors=set()
        for q in s['queue'] + ([s['owner']] if s['owner'] is not None else []):
            require(type(q)==dict)
            require(set(q)==({'actor','priority','lease','enqueued','sequence','checkpoint','token','deadline','dispatch_priority','action_count'} if q is s['owner'] else {'actor','priority','lease','enqueued','sequence','checkpoint'}))
            label(q['actor']); require(q['actor'] not in actors); actors.add(q['actor'])
            require(type(q['priority'])==int and 0<=q['priority']<=100 and type(q['lease'])==int and 10<=q['lease']<=3600)
            require(number(q['enqueued']) and type(q['sequence'])==int)
            if q['checkpoint'] is not None: label(q['checkpoint'])
            if q is s['owner']:
                require(q['token']==f"{s['epoch']}:{s['generation']}" and number(q['deadline']) and number(q['dispatch_priority']) and type(q['action_count'])==int and q['action_count']>=0)
        if s['active'] is not None:
            a=s['active']; require(type(a)==dict and s['owner'] is not None)
            require(set(a) in ({'id','actor','started'},{'id','actor','started','closing_tab'}))
            label(a['id']); require(a['actor']==s['owner']['actor'] and number(a['started']))
        for tab,t in s['tabs'].items():
            label(tab); require(type(t)==dict and set(t)=={'actor','state','unsaved'})
            label(t['actor']); require(t['state'] in ('working','paused','held','complete') and type(t['unsaved'])==bool)
        if s['active'] is not None and 'closing_tab' in s['active']:
            require(s['active']['closing_tab'] in s['tabs'])
            t=s['tabs'][s['active']['closing_tab']]
            require(t['actor']==s['active']['actor'] and t['state']=='complete' and not t['unsaved'])
        if s['shutdown'] is not None:
            sh=s['shutdown']; require(type(sh)==dict and set(sh)=={'actor','token','phase'})
            require(s['owner'] is None and s['active'] is None and not s['tabs'])
            label(sh['actor']); require(sh['token']==f"{s['epoch']}:{s['generation']}" and sh['phase'] in ('prepared','running'))

    def status(self):
        with self.connection(True) as (c,s):
            now = self._now()
            s['software_version'] = VERSION
            s['revision'] = c.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
            s['expired'] = bool(s['owner'] and now >= s['owner']['deadline'])
            s['clock_regressed'] = now < s['last_time']
            s['events'] = [dict(seq=r[0],at=r[1],kind=r[2],actor=r[3]) for r in c.execute('SELECT * FROM events ORDER BY seq DESC LIMIT 50')]
            s['shutdown_blockers'] = (["owner"] if s['owner'] else []) + (["queue"] if s['queue'] else []) + (["retained_tabs"] if s['tabs'] else []) + (["active_action"] if s['active'] else []) + ([] if s['inventory_complete'] else ["unknown_tabs"])
            s['policy'] = dict(max_continuous_hold_seconds=MAX_CONTINUOUS_HOLD,max_queue_wait_seconds=MAX_QUEUE_WAIT,time_slice_seconds=self._time_slice(c),auto_steal=False)
            s['hold_deadline'] = self._hold_deadline(c,s['owner'],create=False) if s['owner'] else None
            s['yield_required'] = bool(s['owner'] and (now>=s['hold_deadline'] or self._should_yield(c,s,now,allow_first_action=True)))
            liveness=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='liveness'").fetchone()
            s['last_keep_alive_at']=c.execute('SELECT seen_at FROM liveness WHERE token=?',(s['owner']['token'],)).fetchone()[0] if s['owner'] and liveness and c.execute('SELECT 1 FROM liveness WHERE token=?',(s['owner']['token'],)).fetchone() else None
            s['first_action_available'] = bool(s['owner'] and not s['owner']['action_count'] and not s['expired'] and not s['frozen'] and now<s['hold_deadline'])
            s['recovery_required'] = bool(s['owner'] and s['expired'])
            s['recovery_route'] = ('wait_for_inflight_then_owner_ack_or_operator' if s['active'] else 'current_owner_confirmed_return_or_operator') if s['recovery_required'] else None
            s['oldest_wait_seconds'] = max([now-q['enqueued'] for q in s['queue']] or [0])
            ready=self._ready_queue(c,s)
            overdue=[q for q in ready if now-q['enqueued']>=MAX_QUEUE_WAIT]
            next_ready=min(overdue,key=lambda q:(q['enqueued'],q['sequence'])) if overdue else (max(ready,key=lambda q:self._rank(q,now)) if ready else None)
            s['next_ready_actor']=next_ready['actor'] if next_ready else None
            s['handoff_ready']=bool(next_ready and s['owner'] and s['active'] is None and s['yield_required'])
            s['work_readiness']=dict(c.execute('SELECT actor,state FROM work_readiness')) if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_readiness'").fetchone() else {}
            exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rejections'").fetchone()
            s['recent_rejections'] = [dict(seq=r[0],at=r[1],op=r[2],actor=r[3],code=r[4]) for r in c.execute('SELECT * FROM rejections ORDER BY seq DESC LIMIT 30')] if exists else []
            s['rejection_history_limit'] = REJECTION_HISTORY
            s['rejection_counts_retained'] = dict(c.execute('SELECT code,COUNT(*) FROM rejections GROUP BY code')) if exists else {}
            exists_diag=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='diagnostics'").fetchone()
            diag_scope='scope' if exists_diag and 'scope' in {r[1] for r in c.execute('PRAGMA table_info(diagnostics)')} else "'inventory-ax-screenshot'"
            s['diagnostics'] = [dict(id=r[0],actor=r[1],original_action=r[2],created_at=r[3],status=r[4],finished_at=r[5],scope=r[6]) for r in c.execute('SELECT id,actor,original_action,created_at,status,finished_at,'+diag_scope+' FROM diagnostics ORDER BY created_at DESC LIMIT 10')] if exists_diag else []
            exists_unknown=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='uncertain_actions'").fetchone()
            s['unknown_action_outcomes'] = [dict(action=r[0],actor=r[1],recorded_at=r[2],outcome=r[3]) for r in c.execute('SELECT * FROM uncertain_actions ORDER BY recorded_at DESC LIMIT 10')] if exists_unknown else []
            exists_manual=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='manual_reconciliations'").fetchone()
            s['manual_reconciliations'] = [dict(action=r[0],actor=r[1],at=r[2],user_ref=r[3],user_at=r[4],observation=r[5],result_ref=r[6],original_outcome=r[7],resolution=r[8]) for r in c.execute('SELECT * FROM manual_reconciliations ORDER BY at DESC LIMIT 10')] if exists_manual else []
            s['notice'] = 'Cooperative only. Expiry never grants another owner.'
            return s

    def _rank(self, q, now): return (q['priority'] + (now-q['enqueued'])/30, -q['sequence'])
    def _grant(self, s, now, c, exclude_actor=None):
        if s['owner'] or s['frozen'] or s['shutdown'] or not s['queue']: return
        ready=self._ready_queue(c,s)
        candidates=[q for q in ready if q['actor']!=exclude_actor] or ready
        if not candidates: return
        overdue=[q for q in candidates if now-q['enqueued']>=MAX_QUEUE_WAIT]
        q=min(overdue,key=lambda q:(q['enqueued'],q['sequence'])) if overdue else max(candidates,key=lambda q:self._rank(q,now))
        s['queue'].remove(q)
        s['generation'] += 1
        q.update(token=f"{s['epoch']}:{s['generation']}", deadline=min(now+q['lease'],now+MAX_CONTINUOUS_HOLD),dispatch_priority=self._rank(q,now)[0],action_count=0)
        s['owner']=q
        c.execute('INSERT INTO grants VALUES(?,?,?)',(q['token'],now,now+MAX_CONTINUOUS_HOLD))
        c.execute('INSERT INTO grant_service VALUES(?,0)',(q['token'],))

    def execute(self, op, request_id, actor, **kw):
        try: return self._execute(op,request_id,actor,**kw)
        except (Conflict,sqlite3.Error) as error:
            code=self._error_code(error)
            error.audit_recorded=self._audit_rejection(op,actor,code)
            error.code=code
            raise

    def _execute(self, op, request_id, actor, **kw):
        label(request_id); label(actor); validate_arguments(op,kw)
        payload=json.dumps(dict(op=op,actor=actor,**kw),sort_keys=True,separators=(',',':'),allow_nan=False)
        with self.connection() as (c,s):
            prior=c.execute('SELECT args,result FROM requests WHERE id=?',(request_id,)).fetchone()
            if prior:
                if prior[0] != payload: raise Conflict('Idempotency key reused with different arguments')
                return dict(strict_json(prior[1]), replay=True)
            now=self._now()
            if now < s['last_time']: raise Conflict('Clock regressed; fail closed until previous time reached')
            s['last_time']=now
            def owner(allow_expired=False):
                o=s['owner']
                if not o or o['actor'] != actor or o['token'] != kw.get('token'): raise Conflict('Stale owner or fencing token')
                if not allow_expired and now >= o['deadline']:
                    if now>=self._hold_deadline(c,o): raise Conflict('Maximum hold reached: checkpoint and return with explicit no-pending acknowledgement')
                    raise Conflict('Lease expired; explicit recovery or original-owner confirmed return required')
                return o
            def quiescent():
                if s['active']: raise Conflict('Action in flight; preserve ownership until completion or verified recovery')
            if op=='acquire':
                priority=kw.get('priority',0); lease=kw.get('lease',120)
                if type(priority)!=int or not 0<=priority<=100: raise Conflict('priority must be integer 0..100')
                if type(lease)!=int or not 10<=lease<=3600: raise Conflict('lease must be integer 10..3600 seconds')
                if s['owner'] and s['owner']['actor']==actor: raise Conflict('Actor already owns resource; use status')
                if any(q['actor']==actor for q in s['queue']): raise Conflict('Actor already queued; use status')
                seq=c.execute('SELECT COALESCE(MAX(seq),0)+1 FROM events').fetchone()[0]
                s['queue'].append(dict(actor=actor,priority=priority,lease=lease,enqueued=now,sequence=seq,checkpoint=None))
                self._grant(s,now,c)
            elif op=='readiness':
                state=kw.get('state')
                if state not in ('preparing','ready'): raise Conflict('readiness state must be preparing or ready')
                c.execute('INSERT OR REPLACE INTO work_readiness VALUES(?,?,?)',(actor,state,now))
                if state=='ready': self._grant(s,now,c)
            elif op=='heartbeat':
                owner(); self._allow_new_action(c,s,now)
                # A manual keep-alive records worker liveness only. It cannot prove
                # that an in-flight tool completed or extend the UI lease.
                c.execute('INSERT OR REPLACE INTO liveness VALUES(?,?)',(kw['token'],now))
            elif op=='begin':
                o=owner(); quiescent()
                self._allow_new_action(c,s,now,allow_first_action=True)
                self._renew_for_progress(c,s,now)
                if kw.get('kind','work') not in ('observation','work'): raise Conflict('begin kind must be observation or work')
                c.execute('INSERT INTO actions VALUES(?)',(label(kw['action']),))
                c.execute('INSERT INTO action_kinds VALUES(?,?)',(kw['action'],kw.get('kind','work')))
                o['action_count']+=1
                s['active']=dict(id=kw['action'],actor=actor,started=now)
            elif op=='inventory':
                owner(); quiescent()
                if type(kw.get('complete'))!=bool: raise Conflict('Explicit inventory completeness required')
                s['inventory_complete']=kw['complete']
            elif op=='tab':
                owner(); quiescent(); tab=label(kw['tab'])
                old=s['tabs'].get(tab)
                if old and old['actor']!=actor: raise Conflict('Tab belongs to another actor')
                state=kw.get('state')
                if state not in ('working','paused','held','complete'): raise Conflict('Invalid tab state')
                if type(kw.get('unsaved'))!=bool: raise Conflict('Explicit unsaved boolean required')
                s['tabs'][tab]=dict(actor=actor,state=state,unsaved=kw['unsaved'])
            elif op=='close-begin':
                o=owner(); quiescent()
                self._allow_new_action(c,s,now,allow_first_action=True)
                self._renew_for_progress(c,s,now)
                tab=kw.get('tab'); t=s['tabs'].get(tab)
                if not t or t['actor']!=actor or t['state']!='complete' or t['unsaved']: raise Conflict('Only own completed saved tabs may close')
                c.execute('INSERT INTO actions VALUES(?)',(label(kw['action']),))
                o['action_count']+=1
                s['active']=dict(id=kw['action'],actor=actor,started=now,closing_tab=tab)
            elif op=='close-end':
                owner(True)
                if c.execute("SELECT 1 FROM uncertain_actions WHERE action=? AND outcome='unknown'",(kw.get('action'),)).fetchone(): raise Conflict('Unresolved original action: diagnostic read does not authorize end')
                if not s['active'] or s['active']['id']!=kw.get('action') or 'closing_tab' not in s['active']: raise Conflict('No matching tab close')
                if type(kw.get('closed'))!=bool: raise Conflict('Explicit tool outcome required')
                if kw['closed']: del s['tabs'][s['active']['closing_tab']]
                s['active']=None
                self._renew_for_progress(c,s,now)
            elif op=='shutdown-prepare':
                if s['owner'] or s['queue'] or s['tabs'] or s['active'] or s['shutdown'] or s['frozen'] or not s['inventory_complete']: raise Conflict('Shutdown blocked: ownership, waiting, tabs, action, frozen state, or unknown inventory')
                s['generation']+=1
                s['shutdown']=dict(actor=actor,token=f"{s['epoch']}:{s['generation']}",phase='prepared')
            elif op in ('shutdown-start','shutdown-end'):
                sh=s['shutdown']
                if not sh or sh['actor']!=actor or sh['token']!=kw.get('token'): raise Conflict('Stale shutdown token')
                if op=='shutdown-start':
                    if sh['phase']!='prepared': raise Conflict('Shutdown already started')
                    if s['queue'] or s['frozen']:
                        s['shutdown']=None; self._grant(s,now,c)
                    else: sh['phase']='running'
                else:
                    if sh['phase']!='running' or type(kw.get('closed'))!=bool: raise Conflict('Shutdown not running or missing tool result')
                    s['shutdown']=None; s['inventory_complete']=False; self._grant(s,now,c)
            elif op=='end':
                owner(True)
                if c.execute("SELECT 1 FROM uncertain_actions WHERE action=? AND outcome='unknown'",(kw.get('action'),)).fetchone(): raise Conflict('Unresolved original action: diagnostic read does not authorize end')
                if not s['active'] or s['active']['id']!=kw.get('action') or 'closing_tab' in s['active']: raise Conflict('No matching generic active action')
                kind=c.execute('SELECT kind FROM action_kinds WHERE action=?',(kw['action'],)).fetchone()
                if kind is None or kind[0]=='work': c.execute('UPDATE grant_service SET completed_work=completed_work+1 WHERE token=?',(kw['token'],))
                s['active']=None
                self._renew_for_progress(c,s,now)
            elif op in ('yield','release'):
                o=owner(True); quiescent()
                if now>=o['deadline'] and kw.get('no_pending_ui') is not True: raise Conflict('Expired lease: confirm no_pending_ui=true for voluntary return; otherwise verified recovery')
                if kw.get('safe') is not True: raise Conflict('Explicit safe-point acknowledgement required')
                checkpoint=label(kw['checkpoint']) if kw.get('checkpoint') else None
                if op=='yield':
                    if not checkpoint: raise Conflict('Yield requires opaque checkpoint reference')
                    o={k:v for k,v in o.items() if k not in ('token','deadline','dispatch_priority','action_count')}
                    o.update(enqueued=now,checkpoint=checkpoint,sequence=c.execute('SELECT COALESCE(MAX(seq),0)+1 FROM events').fetchone()[0])
                    s['queue'].append(o)
                    for t in s['tabs'].values():
                        if t['actor']==actor and t['state']=='working': t['state']='paused'
                s['owner']=None; self._grant(s,now,c,exclude_actor=actor if op=='yield' else None)
                if op=='release': c.execute('DELETE FROM work_readiness WHERE actor=?',(actor,))
            elif op=='cancel':
                before=len(s['queue']); s['queue']=[q for q in s['queue'] if q['actor']!=actor]
                if before==len(s['queue']): raise Conflict('Actor not queued; owners must release')
                c.execute('DELETE FROM work_readiness WHERE actor=?',(actor,))
            elif op=='diagnose-authorize':
                if actor!='coordinator-operator': raise Conflict('Only coordinating operator may authorize diagnostics')
                if not s['frozen'] or not s['owner'] or not s['active']: raise Conflict('Diagnostic read requires frozen original owner and unresolved action')
                revision=c.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
                if kw.get('expected_revision')!=revision or kw.get('expected_token')!=s['owner']['token'] or kw.get('expected_action')!=s['active']['id']: raise Conflict('Diagnostic state changed; re-inspect')
                if kw.get('writer_paused') is not True or kw.get('read_scope') not in ('inventory-ax-screenshot','new-tab-recent-posts'): raise Conflict('Writer pause and exact observation-only scope required')
                c.execute("UPDATE diagnostics SET status='expired' WHERE status='authorized' AND created_at<?",(now-120,))
                if c.execute("SELECT 1 FROM diagnostics WHERE status IN ('authorized','reading')").fetchone(): raise Conflict('Diagnostic already outstanding')
                permit=uuid.uuid4().hex
                c.execute('INSERT INTO diagnostics(id,actor,token,original_action,created_at,status,finished_at,scope) VALUES(?,?,?,?,?,?,NULL,?)',(permit,s['owner']['actor'],s['owner']['token'],s['active']['id'],now,'authorized',kw['read_scope']))
                c.execute('INSERT OR IGNORE INTO uncertain_actions VALUES(?,?,?,?)',(s['active']['id'],s['owner']['actor'],now,'unknown'))
            elif op in ('diagnose-begin','diagnose-end'):
                owner(True)
                if not s['frozen'] or not s['active']: raise Conflict('Diagnostic observation requires preserved frozen action')
                permit=label(kw['permit'])
                row=c.execute('SELECT actor,token,original_action,created_at,status,scope FROM diagnostics WHERE id=?',(permit,)).fetchone()
                if not row or row[:3]!=(actor,kw.get('token'),s['active']['id']): raise Conflict('Diagnostic owner or action mismatch')
                if op=='diagnose-begin':
                    if row[4]!='authorized' or now-row[3]>120: raise Conflict('Diagnostic permit used or expired; operator decision required')
                    if kw.get('read_scope')!=row[5]: raise Conflict('Diagnostic scope must match operator authorization')
                    c.execute("UPDATE diagnostics SET status='reading' WHERE id=?",(permit,))
                else:
                    if row[4]!='reading' or type(kw.get('read_completed'))!=bool: raise Conflict('No matching diagnostic read or missing terminal result')
                    c.execute('UPDATE diagnostics SET status=?,finished_at=? WHERE id=?',('read_complete' if kw['read_completed'] else 'read_failed',now,permit))
            elif op=='manual-reconcile':
                if actor!='coordinator-operator' or not s['frozen'] or not s['owner'] or not s['active']: raise Conflict('Manual reconciliation requires operator and frozen original action')
                revision=c.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
                if kw.get('expected_revision')!=revision or kw.get('expected_token')!=s['owner']['token'] or kw.get('expected_action')!=s['active']['id']: raise Conflict('Reconciliation state changed; re-inspect')
                if any(kw.get(k) is not True for k in ('writer_paused','no_known_running_invocations','user_completed','result_verified')): raise Conflict('Explicit current-worker stop, invocation status, user result and fresh result verification required')
                if c.execute("SELECT 1 FROM diagnostics WHERE status='reading'").fetchone(): raise Conflict('Diagnostic read still running')
                manual_at=kw.get('user_at')
                if type(manual_at) not in (int,float) or not math.isfinite(manual_at) or not s['active']['started']<=manual_at<=now: raise Conflict('Invalid manual-result timestamp')
                observation=label(kw['observation']);user_ref=label(kw['user_ref']);result_ref=label(kw['result_ref'])
                d=c.execute('SELECT actor,token,original_action,created_at,status,finished_at,scope FROM diagnostics WHERE id=?',(observation,)).fetchone()
                if not d or d[:3]!=(s['owner']['actor'],s['owner']['token'],s['active']['id']) or d[4]!='read_complete' or d[6]!='new-tab-recent-posts' or d[3]<manual_at or d[5] is None or d[5]<manual_at: raise Conflict('Fresh post-manual observation required')
                unknown=c.execute('SELECT outcome FROM uncertain_actions WHERE action=?',(s['active']['id'],)).fetchone()
                if not unknown or unknown[0]!='unknown': raise Conflict('Original uncertainty record required')
                original_action=s['active']['id'];original_actor=s['owner']['actor']
                c.execute('INSERT INTO manual_reconciliations VALUES(?,?,?,?,?,?,?,?,?)',(original_action,original_actor,now,user_ref,manual_at,observation,result_ref,'unknown','manual_verified'))
                c.execute("UPDATE diagnostics SET status='revoked' WHERE original_action=? AND status='authorized'",(original_action,))
                # Retire the logical hold on explicit manual-result reconciliation,
                # not on a fabricated success/failure or claimed backend drain.
                s['active']=None;s['owner']=None;s['frozen']=False;s['inventory_complete']=False
                self._grant(s,now,c)
            elif op=='freeze': s['frozen']=True
            elif op=='recover':
                if c.execute("SELECT 1 FROM diagnostics WHERE status='reading'").fetchone(): raise Conflict('Diagnostic read in flight; wait for its terminal result')
                # Freeze first, inspect external tools, then compare exact revision.
                if not s['frozen']: raise Conflict('Freeze before recovery inspection')
                revision=c.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
                if kw.get('expected_revision')!=revision: raise Conflict('State changed since recovery inspection')
                if kw.get('old_worker_quiescent') is not True: raise Conflict('Old worker stopped or acknowledged no future submissions required')
                if kw.get('verified_idle') is not True: raise Conflict('External verification of no running UI action required')
                label(kw['evidence'])
                if kw.get('expected_shutdown_token') != (s['shutdown']['token'] if s['shutdown'] else None): raise Conflict('Shutdown changed; re-inspect')
                if kw.get('expected_token') != (s['owner']['token'] if s['owner'] else None): raise Conflict('Recovery state changed; re-inspect')
                s['active']=None; s['owner']=None; s['shutdown']=None; s['frozen']=False; s['inventory_complete']=False
                self._grant(s,now,c)
            else: raise Conflict('Unknown operation')
            self._validate(s)
            result=dict(ok=True,revision=c.execute('SELECT COALESCE(MAX(seq),0)+1 FROM events').fetchone()[0],replay=False,op=op,actor=actor,owner=s['owner'],queue=s['queue'],active=s['active'],frozen=s['frozen'],shutdown=s['shutdown'])
            if op.startswith('diagnose-'):
                result['diagnostic']=dict(id=permit,scope=c.execute('SELECT scope FROM diagnostics WHERE id=?',(permit,)).fetchone()[0],status=c.execute('SELECT status FROM diagnostics WHERE id=?',(permit,)).fetchone()[0],original_action=s['active']['id'],original_outcome='unknown')
            c.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(s),))
            c.execute('INSERT INTO events(at,kind,actor) VALUES(?,?,?)',(now,op,actor))
            c.execute('INSERT INTO requests VALUES(?,?,?)',(request_id,payload,json.dumps(result)))
            return result

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--db',required=True)
    p.add_argument('operation',choices=['init','status','dashboard','acquire','heartbeat','readiness','begin','end','yield','release','cancel','freeze','recover','tab','close-begin','close-end','shutdown-prepare','shutdown-start','shutdown-end','inventory','diagnose-authorize','diagnose-begin','diagnose-end','manual-reconcile'])
    p.add_argument('--actor'); p.add_argument('--request'); p.add_argument('--args',default='{}'); p.add_argument('--output')
    a=p.parse_args(); co=Coordinator(a.db)
    try:
        if len(a.args.encode('utf-8'))>16384: raise Conflict('Request payload too large')
        parsed=strict_json(a.args)
        if type(parsed)!=dict: raise Conflict('Arguments must be a JSON object')
        if a.operation in ('status','dashboard') and parsed: raise Conflict('Read-only commands accept no argument payload')
        if a.operation in ('init','status','dashboard') and (a.actor is not None or a.request is not None): raise Conflict('This command accepts no actor or request identifier')
        if a.operation!='dashboard' and a.output is not None: raise Conflict('Output is only valid for dashboard')
        if a.operation=='init': result=co.initialize(**parsed)
        elif a.operation in ('status','dashboard'):
            result=co.status()
            if a.operation=='dashboard':
                if not a.output: raise Conflict('--output required')
                data=html.escape(json.dumps(result,ensure_ascii=False,indent=2))
                write_dashboard(a.output,'<!doctype html><meta charset="utf-8"><title>Resource status</title><style>body{font:16px system-ui;background:#101827;color:#e5e7eb;padding:32px}pre{white-space:pre-wrap}</style><h1>Shared resource status</h1><p>Read-only snapshot. Regenerate to refresh. Cooperative control.</p><pre>'+data+'</pre>')
        else: result=co.execute(a.operation,a.request,a.actor,**parsed)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (Conflict,sqlite3.Error,ValueError,KeyError,TypeError,OSError) as e:
        code=getattr(e,'code','INVALID_REQUEST')
        next_steps={'LEASE_EXPIRED':'No UI. Same owner may return only with safe=true,no_pending_ui=true and no active call; otherwise operator freeze/recover.', 'EXPIRED_RETURN_ACK_REQUIRED':'Confirm the original worker has no pending UI calls, or request operator recovery.', 'YIELD_REQUIRED':'Checkpoint and yield at this safe boundary; recheck the returned owner/token.', 'MAX_HOLD_REACHED':'Checkpoint and yield/release with safe=true,no_pending_ui=true only after confirming no pending calls; otherwise operator recovery.', 'ACTION_IN_FLIGHT':'Wait for the exact tool result; never replay or steal ownership.', 'FROZEN':'No new UI; contact the coordinating parent.'}
        print(json.dumps(dict(ok=False,error=str(e),code=code,next_step=next_steps.get(code,'Inspect state and request context; do not bypass the rejection.'),audit_recorded=getattr(e,'audit_recorded',False)))); raise SystemExit(2)
if __name__=='__main__': main()
