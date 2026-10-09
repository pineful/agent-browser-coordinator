#!/usr/bin/env python3
"""Two independent mock workers; no browser calls or external state changes."""
import json, multiprocessing as mp, tempfile, time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from agent_browser_coordinator import Coordinator

def worker(db, name, start, queued, done):
 c=Coordinator(db); n=0
 def call(op,**kw):
  nonlocal n; n+=1; return c.execute(op,f'{name}-{n}',name,**kw)
 if name=='normal':
  t=call('acquire',priority=10)['owner']['token']
  call('tab',token=t,tab='normal-tab',state='working',unsaved=False)
  call('inventory',token=t,complete=True)
  call('begin',token=t,action='normal-work'); start.set()
  assert queued.wait(5); call('end',token=t,action='normal-work')
  call('yield',token=t,safe=True,checkpoint='normal-cp')
  assert done.wait(5)
  s=c.status(); assert s['owner']['actor']==name; t=s['owner']['token']
  assert s['tabs']['normal-tab']['state']=='paused'
  call('tab',token=t,tab='normal-tab',state='complete',unsaved=False)
  call('close-begin',token=t,tab='normal-tab',action='normal-close')
  # A real adapter closes only its mapped tab here. This is a mock success.
  call('close-end',token=t,action='normal-close',closed=True)
  call('release',token=t,safe=True)
 else:
  assert start.wait(5); call('acquire',priority=100); queued.set()
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   s=c.status()
   if s['owner']['actor']==name: break
   time.sleep(.01)
  else: raise RuntimeError('handoff timeout')
  t=s['owner']['token']; assert 'normal-tab' in s['tabs']
  call('begin',token=t,action='urgent-work'); call('end',token=t,action='urgent-work')
  call('release',token=t,safe=True); done.set()

def main():
 with tempfile.TemporaryDirectory() as d:
  db=str(Path(d)/'mock.db'); c=Coordinator(db); c.initialize('mock-ui',True)
  signals=[mp.Event() for _ in range(3)]
  processes=[mp.Process(target=worker,args=(db,name,*signals)) for name in ('normal','urgent')]
  for p in processes:p.start()
  for p in processes:
   p.join(10)
   if p.is_alive(): p.terminate(); p.join(); raise RuntimeError('mock worker stuck')
   if p.exitcode: raise RuntimeError(f'mock worker failed {p.exitcode}')
  s=c.status(); assert not s['owner'] and not s['queue'] and not s['tabs']
  r=c.execute('shutdown-prepare','shutdown-1','operator'); t=r['shutdown']['token']
  c.execute('shutdown-start','shutdown-2','operator',token=t)
  c.execute('shutdown-end','shutdown-3','operator',token=t,closed=True)
  print(json.dumps({'result':'PASS','workers':2,'checks':['priority handoff','tab preservation','resume','own-tab cleanup','idle shutdown'],'real_browser_used':False},indent=2))
if __name__=='__main__':main()
