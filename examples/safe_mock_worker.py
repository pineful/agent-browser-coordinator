"""Disposable mock: no UI, accounts, networking, or production-state discovery."""
import json,sys,tempfile,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from agent_browser_coordinator import Coordinator

def main():
    with tempfile.TemporaryDirectory(prefix='abc-example-') as root:
        co=Coordinator(Path(root)/'mock.db')
        co.initialize('synthetic-ui',confirmed_idle=True)
        def call(op,**kwargs):return co.execute(op,uuid.uuid4().hex,'example-worker',**kwargs)
        grant=call('acquire',priority=10,lease=120)
        assert not grant['replay'] and grant['owner']['actor']=='example-worker'
        token=grant['owner']['token'];action=uuid.uuid4().hex
        begin=call('begin',token=token,action=action)
        assert not begin['replay'] and begin['active']['id']==action
        # Replace this mock only with one authorized finite call. An unknown
        # outcome must not be hidden by an unconditional finally/end.
        mock_result={'observed':True}
        assert mock_result['observed']
        call('end',token=token,action=action)
        call('release',token=token,safe=True)
        assert co.status()['owner'] is None
        print(json.dumps({'mock_completed':True,'real_browser_calls':0}))
if __name__=='__main__':main()
