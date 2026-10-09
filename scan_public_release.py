#!/usr/bin/env python3
"""Check the public allowlist, forbidden payloads, likely secrets and local links.

This deterministic scan is a release check, not proof that all secrets are absent.
A human must review every changed allowlisted file before publishing.
"""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PATTERNS={
    'private_workspace': re.compile('/work'+'space/(?:scratch|shared)/'),
    'home_path':re.compile('/(?:home|Users|root)/[A-Za-z0-9_.-]+/'),
    'private_drive_link':re.compile('drive.google.com/(?:file/d|drive/folders)/[A-Za-z0-9_-]{15,}'),
    'conversation_ref':re.compile('Sent'+'inel_[0-9a-f]{20,}'),
    'personal_skill_id':re.compile('skill-'+'[0-9a-f]{25,}'),
    'private_key':re.compile('BEGIN '+'(?:RSA |EC |OPENSSH )?PRIVATE KEY'),
    'github_secret':re.compile('(?:gh'+'[pousr]_[A-Za-z0-9]{30,}|github'+'_pat_[A-Za-z0-9_]{30,})'),
    'cloud_secret':re.compile('(?:AK'+'IA[0-9A-Z]{16}|sk'+'-[A-Za-z0-9_-]{32,})'),
    'bearer_value':re.compile('Bearer '+'[A-Za-z0-9._-]{24,}'),
}
def main():
    names=json.loads((ROOT/'RELEASE_ALLOWLIST.json').read_text());errors=[]
    if len(names)!=len(set(names)):errors.append('duplicate allowlist path')
    for n in names:
        p=ROOT/n
        if p.is_symlink() or not p.is_file():errors.append(n+': missing or symlink');continue
        if any(x in Path(n).parts for x in ['runtime','.git','.venv','__pycache__']) or p.suffix in {'.db','.sqlite','.log','.png','.jpg','.mp4','.wav'}:
            errors.append(n+': forbidden payload type')
        try:t=p.read_text()
        except UnicodeDecodeError:errors.append(n+': binary payload');continue
        for label,rx in PATTERNS.items():
            if rx.search(t):errors.append(n+': '+label)
        if p.suffix=='.md':
            for dest in re.findall(r'\[[^\]]*\]\(([^)]+)\)',t):
                target=dest.split('#',1)[0]
                if target and not re.match(r'^[a-z][a-z0-9+.-]*:',target) and not (p.parent/target).is_file():
                    errors.append(n+': broken local link '+target)
    print(json.dumps({'files_scanned':len(names),'findings':errors,'manual_review_required':True},indent=2))
    return bool(errors)
if __name__=='__main__':raise SystemExit(main())
