"""Disposable mock: no UI, accounts, networking, or production-state discovery."""
import json,sys,tempfile,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from agent_browser_coordinator import Coordinator
from agent_browser_coordinator.guard import run_guarded

def main():
    with tempfile.TemporaryDirectory(prefix='abc-example-') as root:
        co=Coordinator(Path(root)/'mock.db')
        co.initialize('synthetic-ui',confirmed_idle=True)
        def call(op,**kwargs):return co.execute(op,uuid.uuid4().hex,'example-worker',**kwargs)
        grant=call('acquire',priority=10,lease=120)
        if grant['replay'] or grant['owner']['actor']!='example-worker':
            raise RuntimeError('No fresh owner grant')
        token=grant['owner']['token'];action=uuid.uuid4().hex
        mock_result=run_guarded(co,actor='example-worker',token=token,action=action,
                                begin_request=uuid.uuid4().hex,end_request=uuid.uuid4().hex,
                                kind='observation',call=lambda:(True,{'observed':True}))
        if not mock_result['observed']: raise RuntimeError('Mock observation failed')
        call('release',token=token,safe=True)
        if co.status()['owner'] is not None: raise RuntimeError('Owner was not released')
        print(json.dumps({'mock_completed':True,'real_browser_calls':0}))
if __name__=='__main__':main()
