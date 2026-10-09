#!/usr/bin/env python3
"""Run only disposable synthetic tests; never discovers a runtime database."""
import json,re,subprocess,sys
from pathlib import Path
from verify_install import minimal_environment
ROOT=Path(__file__).resolve().parent
COMMANDS=[['-m','unittest','discover','-s','tests','-v'],['reviewer_test.py'],['reviewer_continuity_test.py'],['review_recovery_test.py'],['demo.py'],['examples/safe_mock_worker.py'],['scan_public_release.py']]
def main():
    if sys.flags.optimize: raise RuntimeError("Do not disable verification assertions")
    results=[]
    for args in COMMANDS:
        result=subprocess.run([sys.executable,*args],cwd=ROOT,capture_output=True,text=True,timeout=120,env=minimal_environment())
        count=re.search(r'Ran (\d+) tests?',result.stderr)
        results.append({'command':args,'returncode':result.returncode,'test_methods':int(count.group(1)) if count else 0})
        if result.returncode:
            print(result.stdout);print(result.stderr,file=sys.stderr);return result.returncode
    print(json.dumps({'checks':results,'test_methods':sum(item['test_methods'] for item in results),'real_ui_used':False,'live_state_used':False},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
