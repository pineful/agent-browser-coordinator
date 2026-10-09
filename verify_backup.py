#!/usr/bin/env python3
"""Verify a known backup into a NEW isolated folder. Never activates a resource."""
import argparse,hashlib,io,json,stat,subprocess,sys,zipfile
from pathlib import Path
from release_files import no_symlink_path,new_directory,write_new,trusted_directory
from verify_install import minimal_environment
ROOT=Path(__file__).resolve().parent
ALLOWED=set(json.loads((ROOT/'RELEASE_ALLOWLIST.json').read_text()))
BASE=ALLOWED
OPTIONAL=set()
def unique_object(pairs):
 result={}
 for key,value in pairs:
  if key in result: raise ValueError('Duplicate manifest key')
  result[key]=value
 return result

def restore(archive,expected,destination):
 archive=Path(archive); dest=no_symlink_path(destination)
 trusted_directory(dest.parent)
 if len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected): raise ValueError('Invalid SHA-256')
 with archive.open('rb') as stream: archive_bytes=stream.read(8_000_001)
 if len(archive_bytes)>8_000_000: raise ValueError('Archive too large')
 if hashlib.sha256(archive_bytes).hexdigest()!=expected: raise ValueError('Backup SHA-256 mismatch; do not execute')
 if dest.exists() or dest.is_symlink(): raise ValueError('Destination must not exist; live state must never be overwritten')
 with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
  entries=z.infolist(); names=[i.filename for i in entries]
  if any(n.startswith('/') or '..' in Path(n).parts or '\\' in n for n in names) or len(names)!=len(set(names)) or set(names)-BASE-OPTIONAL-{'MANIFEST.json'}: raise ValueError('Unexpected or duplicate archive paths')
  if sum(i.file_size for i in entries)>8_000_000 or any(stat.S_ISLNK(i.external_attr>>16) for i in entries): raise ValueError('Unsafe archive type or size')
  manifest=json.loads(z.read('MANIFEST.json'),object_pairs_hook=unique_object)
  if type(manifest)!=dict or not BASE<=set(manifest) or set(manifest)!=(set(names)-{'MANIFEST.json'}): raise ValueError('Invalid manifest')
  data={n:z.read(n) for n in manifest}
  if not all(hashlib.sha256(v).hexdigest()==manifest[n] for n,v in data.items()): raise ValueError('Manifest content mismatch')
 new_directory(dest)
 for n,v in data.items():
  path=dest/n;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);write_new(path,v)
 write_new(dest/'MANIFEST.json',json.dumps(manifest,indent=2).encode())
 results=[]
 commands=[['validate_release.py']]
 for args in commands:
  r=subprocess.run([sys.executable,*args],cwd=dest,capture_output=True,text=True,timeout=120,env=minimal_environment())
  results.append(dict(command=args,returncode=r.returncode))
  if r.returncode: raise RuntimeError('Isolated restore test failed: '+r.stdout+r.stderr)
 return dict(sha256=expected,destination=str(dest.resolve()),tests=results,activated=False,live_database_touched=False)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive');p.add_argument('--sha256',required=True);p.add_argument('--destination',required=True);a=p.parse_args()
 print(json.dumps(restore(a.archive,a.sha256,a.destination),indent=2))
if __name__=='__main__':main()
