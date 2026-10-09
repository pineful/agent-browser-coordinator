#!/usr/bin/env python3
"""Hash-check a trusted wheel, install offline in a fresh venv, and run smoke checks.

This is environment isolation, not a sandbox for untrusted package code.
"""
import argparse,hashlib,io,json,os,re,subprocess,sys,tempfile,zipfile
from email.parser import BytesParser
from pathlib import Path
from coordinator import VERSION
from release_files import safe_read
ROOT=Path(__file__).resolve().parent
SMOKE='''import json,tempfile
from pathlib import Path
import agent_browser_coordinator as package
from importlib.metadata import version as distribution_version
if distribution_version('agent-browser-coordinator') != EXPECTED_VERSION: raise RuntimeError('Distribution metadata version mismatch')
from agent_browser_coordinator import Coordinator
if package.__version__ != EXPECTED_VERSION: raise RuntimeError('Installed version mismatch')
with tempfile.TemporaryDirectory(prefix='abc-installed-state-') as work:
    missing=Path(work)/'missing.db'
    try: Coordinator(missing).status()
    except Exception: pass
    else: raise RuntimeError('Missing state was accepted')
    if missing.exists(): raise RuntimeError('Missing database was created')
    co=Coordinator(Path(work)/'mock.db');co.initialize('synthetic-ui',True)
    result=co.execute('acquire','installed-acquire','mock-worker')
    token=result['owner']['token']
    begin=co.execute('begin','installed-begin','mock-worker',token=token,action='mock-action')
    if begin['replay']: raise RuntimeError('Unexpected replay')
    co.execute('end','installed-end','mock-worker',token=token,action='mock-action')
    co.execute('release','installed-release','mock-worker',token=token,safe=True)
    if co.status()['owner'] is not None: raise RuntimeError('Mock release failed')
print(json.dumps({'version':package.__version__,'module':str(Path(package.__file__).resolve()),'mock_passed':True}))
'''
def minimal_environment():
    # No inherited credentials, HOME override, Python optimization, or pip config.
    return {'PATH':os.defpath,'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
def run(command,**kwargs):
    return subprocess.run(command,env=minimal_environment(),capture_output=True,text=True,timeout=120,check=True,**kwargs)
def verify(wheel,expected):
    if not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('Invalid SHA-256')
    wheel=Path(wheel).absolute()
    if wheel.name!='agent_browser_coordinator-'+VERSION+'-py3-none-any.whl':raise ValueError('Unexpected wheel filename/version')
    data=safe_read(wheel.parent,wheel.name)
    if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Wheel SHA-256 mismatch; nothing executed')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=[i.filename for i in archive.infolist()]
        metadata_name='agent_browser_coordinator-'+VERSION+'.dist-info/METADATA'
        if len(names)!=len(set(names)) or metadata_name not in names:raise ValueError('Invalid wheel metadata membership')
        if sum(i.file_size for i in archive.infolist())>8_000_000:raise ValueError('Wheel expanded size limit exceeded')
        metadata=BytesParser().parsebytes(archive.read(metadata_name))
        if metadata.get_all('Name')!=['agent-browser-coordinator'] or metadata.get_all('Version')!=[VERSION]:raise ValueError('Wheel distribution metadata mismatch')
    with tempfile.TemporaryDirectory(prefix='abc-clean-install-') as work:
        root=Path(work);copy=root/wheel.name;copy.write_bytes(data)
        envdir=root/'venv'
        run([sys.executable,'-I','-m','venv',str(envdir)],cwd=root)
        python=envdir/'bin/python';cli=envdir/'bin/agent-browser-coordinator'
        run([str(python),'-I','-m','pip','--isolated','--disable-pip-version-check','--no-cache-dir','install','--no-index','--no-deps',str(copy)],cwd=root)
        result=run([str(python),'-I','-c',SMOKE.replace('EXPECTED_VERSION',repr(VERSION))],cwd=root)
        report=json.loads(result.stdout)
        if Path(report['module']).is_relative_to(ROOT):raise RuntimeError('Source checkout shadowed installed wheel')
        result=run([str(cli),'--version'],cwd=root)
        if result.stdout.strip()!=VERSION:raise RuntimeError('CLI version mismatch')
        missing=root/'never-created.db'
        result=subprocess.run([str(cli),'--db',str(missing),'status'],cwd=root,env=minimal_environment(),capture_output=True,text=True,timeout=30)
        if result.returncode!=2 or missing.exists():raise RuntimeError('Missing-DB safety check failed')
        return {'wheel':wheel.name,'sha256':expected,'offline_fresh_venv':True,'import_outside_source':True,'cli_version':VERSION,'mock_passed':report['mock_passed'],'missing_db_not_created':True,'real_ui_used':False,'untrusted_code_sandbox':False}
def main():
    p=argparse.ArgumentParser();p.add_argument('wheel');p.add_argument('--sha256',required=True);a=p.parse_args()
    print(json.dumps(verify(a.wheel,a.sha256),indent=2))
if __name__=='__main__':main()
