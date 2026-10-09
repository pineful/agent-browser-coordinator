"""Narrow file helpers for trusted local release directories.

No protection against malicious code running as the same OS user is claimed.
"""
import os,stat
from pathlib import Path

def no_symlink_path(path):
    p=Path(os.path.abspath(os.fspath(path)))
    for item in [p,*p.parents]:
        if item.is_symlink():raise ValueError('Symlink paths are not supported')
    return p

def trusted_directory(path):
    p=no_symlink_path(path)
    st=p.stat()
    if not stat.S_ISDIR(st.st_mode) or st.st_mode & 0o022:
        raise ValueError('Use an existing directory without group/world write permission')
    return p

def new_directory(path):
    p=no_symlink_path(path);trusted_directory(p.parent)
    if os.path.lexists(p):raise ValueError('Destination must not exist')
    p.mkdir(mode=0o700)
    return p

def safe_read(root,name,limit=8_000_000):
    root=trusted_directory(root)
    if not isinstance(name,str) or name.startswith('/') or '\\' in name or '..' in Path(name).parts:
        raise ValueError('Unsafe release path')
    p=no_symlink_path(root/name)
    if not p.is_relative_to(root):raise ValueError('Path escaped source root')
    for parent in p.parents:
        if parent==root.parent:break
        trusted_directory(parent)
    before=p.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):raise ValueError('Only regular source files are allowed')
    fd=os.open(p,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(fd,'rb') as stream:
        opened=os.fstat(stream.fileno())
        if (before.st_dev,before.st_ino)!=(opened.st_dev,opened.st_ino):raise ValueError('Source identity changed')
        data=stream.read(limit+1);after=os.fstat(stream.fileno())
    final=p.stat(follow_symlinks=False)
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    if len(data)>limit or identity(opened)!=identity(after) or identity(after)!=identity(final):
        raise ValueError('Source size or identity changed while reading')
    return data

def write_new(path,data):
    p=no_symlink_path(path);trusted_directory(p.parent)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(data)
    return p
