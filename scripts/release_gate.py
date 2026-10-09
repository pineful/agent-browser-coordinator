#!/usr/bin/env python3
"""One mandatory pre-release gate: tests, security scans, build, install, restore.

Run only on a reviewed/trusted checkout. This is not a sandbox for hostile code.
No publication, credentials, network upload, or production state is involved.
"""
import argparse,hashlib,json,os,re,subprocess,sys,tarfile,tempfile,zipfile
from pathlib import Path
from agent_browser_coordinator import VERSION
from .release_files import safe_read,write_new,new_directory,no_symlink_path,trusted_directory
from .verify_install import minimal_environment,verify as verify_wheel
from .verify_backup import restore
from .scan_public_release import PATTERNS
ROOT=Path(__file__).resolve().parents[1]

def checked(command,cwd,timeout=180):
    env=minimal_environment();env['SOURCE_DATE_EPOCH']='1791504000'
    r=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout)
    if r.returncode:raise RuntimeError('Required check failed: '+str(command[1:])+'\n'+r.stdout+r.stderr)
    return r

def artifact_scan(path,expected_sources):
    entries=[]
    if path.suffix in {'.zip','.whl'}:
        with zipfile.ZipFile(path) as z:
            infos=z.infolist()
            if len({i.filename for i in infos})!=len(infos):raise ValueError('Duplicate artifact members')
            entries=[(i.filename,z.read(i)) for i in infos if not i.is_dir()]
    else:
        with tarfile.open(path) as t:
            members=t.getmembers()
            if len({i.name for i in members})!=len(members):raise ValueError('Duplicate sdist members')
            if any(not (i.isfile() or i.isdir()) for i in members):raise ValueError('Non-regular sdist member')
            entries=[(i.name,t.extractfile(i).read()) for i in members if i.isfile()]
    if sum(len(v) for _,v in entries)>8_000_000:raise ValueError('Artifact expanded size limit exceeded')
    for n,b in entries:
        if n.startswith('/') or '..' in Path(n).parts or '\\' in n:raise ValueError('Unsafe artifact path')
        text=b.decode('utf-8')
        for label,pattern in PATTERNS.items():
            if pattern.search(text):raise ValueError('Artifact content scan finding: '+label)
    if path.suffix=='.whl':
        expected={n[4:]:v for n,v in expected_sources.items() if n.startswith('src/agent_browser_coordinator/')}
        metadata_prefix='agent_browser_coordinator-'+VERSION+'.dist-info/'
        metadata={'licenses/LICENSE','METADATA','WHEEL','entry_points.txt','top_level.txt','RECORD'}
        actual=dict(entries)
        if set(actual)!=set(expected)|{metadata_prefix+n for n in metadata}:raise ValueError('Unexpected wheel membership')
        if any(actual[n]!=b for n,b in expected.items()):raise ValueError('Wheel source differs from reviewed snapshot')
    elif path.name.endswith('.tar.gz'):
        prefix='agent_browser_coordinator-'+VERSION+'/'
        actual={n[len(prefix):]:b for n,b in entries if n.startswith(prefix)}
        extras={'PKG-INFO','setup.cfg'}|{'src/agent_browser_coordinator.egg-info/'+n for n in ['PKG-INFO','SOURCES.txt','dependency_links.txt','entry_points.txt','top_level.txt']}
        if len(actual)!=len(entries) or set(actual)!=set(expected_sources)|extras:raise ValueError('Unexpected sdist membership')
        if any(actual[n]!=b for n,b in expected_sources.items()):raise ValueError('Sdist source differs from reviewed snapshot')
    else:
        actual=dict(entries)
        if set(actual)!=set(expected_sources)|{'MANIFEST.json'}:raise ValueError('Unexpected source ZIP membership')
        if any(actual[n]!=b for n,b in expected_sources.items()):raise ValueError('ZIP source differs from reviewed snapshot')
    return {'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'members':len(entries)}

def gate(output):
    if sys.flags.optimize:raise RuntimeError('Do not run release checks with optimization')
    output=no_symlink_path(output);trusted_directory(output.parent)
    if os.path.lexists(output):raise ValueError('Release output directory must not exist')
    validation=checked([sys.executable,'-m','scripts.validate_release'],ROOT)
    source_names=json.loads(safe_read(ROOT,'config/release-allowlist.json'))
    if len(source_names)!=len(set(source_names)):raise ValueError('Duplicate allowlist entry')
    sources={n:safe_read(ROOT,n) for n in source_names}
    new_directory(output)
    with tempfile.TemporaryDirectory(prefix='abc-release-gate-') as work:
        work=Path(work);stage=new_directory(work/'source')
        for name,data in sources.items():
            p=stage/name;p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);write_new(p,data)
        checked([sys.executable,'-m','pip','--isolated','--no-cache-dir','wheel','--no-index','--no-deps','--no-build-isolation','--wheel-dir',str(output),'.'],stage)
        checked([sys.executable,'-c','from setuptools import build_meta; build_meta.build_sdist('+repr(str(output))+')'],stage)
        checked([sys.executable,'-m','scripts.package_release','--output-dir',str(output)],stage)
        wheel=output/('agent_browser_coordinator-'+VERSION+'-py3-none-any.whl')
        sdist=output/('agent_browser_coordinator-'+VERSION+'.tar.gz')
        source_zip=output/('agent-browser-coordinator-'+VERSION+'-source.zip')
        artifacts=[artifact_scan(p,sources) for p in [wheel,sdist,source_zip]]
        installation=verify_wheel(wheel,artifacts[0]['sha256'])
        # The checksum is anchored to the trusted, reviewed snapshot built above.
        restored=restore(source_zip,artifacts[2]['sha256'],work/'restored')
        if restored['activated']:raise RuntimeError('Source restore unexpectedly activated a resource')
    result={'ok':True,'version':VERSION,'source_files':len(sources),'tests':json.loads(validation.stdout),'artifacts':artifacts,'fresh_venv_install':installation,'restored_source_validation':'passed','real_ui_used':False,'production_state_used':False,'hosted_ci':'reference only; not run','security_guarantee':False}
    write_new(output/'RELEASE_VALIDATION.json',(json.dumps(result,indent=2)+'\n').encode())
    write_new(output/'SHA256SUMS',(''.join(a['sha256']+'  '+a['file']+'\n' for a in artifacts)).encode())
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);args=p.parse_args()
    try:result=gate(args.output_dir)
    except Exception as error:
        print(json.dumps({'ok':False,'error':str(error),'release_allowed':False}));return 1
    print(json.dumps(result,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
