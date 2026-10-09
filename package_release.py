#!/usr/bin/env python3
"""Build an explicitly allowlisted source archive; never overwrite existing files."""
import argparse,hashlib,io,json,os,stat,zipfile
from pathlib import Path
from coordinator import VERSION
from release_files import safe_read,write_new,new_directory,trusted_directory,no_symlink_path
ROOT=Path(__file__).resolve().parent
FILES=json.loads((ROOT/'RELEASE_ALLOWLIST.json').read_text())
def build(output_dir):
    if len(FILES)!=len(set(FILES)):raise ValueError('Duplicate release path')
    payload={name:safe_read(ROOT,name) for name in FILES}
    manifest={n:hashlib.sha256(b).hexdigest() for n,b in payload.items()}
    dest=no_symlink_path(output_dir)
    if not dest.exists():new_directory(dest)
    trusted_directory(dest)
    out=dest/('agent-browser-coordinator-'+VERSION+'-source.zip')
    checksum=out.with_suffix(out.suffix+'.sha256')
    if os.path.lexists(out) or os.path.lexists(checksum):raise ValueError('Release output exists; use a new output directory')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in [*payload.items(),('MANIFEST.json',json.dumps(manifest,indent=2,sort_keys=True).encode())]:
            info=zipfile.ZipInfo(name,date_time=(2026,10,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|0o644)<<16
            z.writestr(info,data)
    data=buffer.getvalue();digest=hashlib.sha256(data).hexdigest()
    write_new(out,data);write_new(checksum,(digest+'  '+out.name+'\n').encode())
    return {'archive':out.name,'sha256':digest,'payloads':len(payload),'runtime_state_included':False}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',default=str(ROOT/'dist'));args=p.parse_args()
    print(json.dumps(build(args.output_dir),indent=2))
if __name__=='__main__':main()
