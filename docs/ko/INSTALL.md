# 설치

Python 3.10 이상과 로컬 POSIX 파일시스템을 사용합니다. 이번 검증은 격리된 Linux 환경에서 수행하며 Windows·네트워크 파일시스템·모든 Python/플랫폼 조합의 검증을 뜻하지 않습니다. SQLite는 Python에 포함됩니다. 설치만으로 브라우저·포트·인증정보·서비스를 설정하지 않습니다.

이 저장소를 다운로드하거나 clone한 뒤 해당 디렉터리에서 실행합니다.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
agent-browser-coordinator --version
python -m agent_browser_coordinator --version
```

소스 빌드에는 설정된 Python 패키지 저장소의 Setuptools를 사용합니다. 오프라인 설치는 출처와 SHA-256을 확인한 릴리스 wheel을 사용합니다.

```sh
python -m pip install --no-index --no-deps ./agent_browser_coordinator-0.3.4-py3-none-any.whl
python validate_release.py
python package_release.py
```

아래 두 검증 명령은 소스 checkout에서 실행합니다. PyPI에 게시됐다고 주장하지 않으므로 비슷한 이름의 다른 패키지를 대신 설치하지 마세요. 제거는 `python -m pip uninstall agent-browser-coordinator`이며 작업자 중지·운영 DB 삭제는 별도입니다.

[설정](CONFIGURATION.md) · [사용 예제](USAGE.md) · [복구](RECOVERY.md)
