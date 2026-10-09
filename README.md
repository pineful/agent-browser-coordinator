# Agent Browser Coordinator

[한국어](README.md) · [English](README.en.md) · [日本語](README.ja.md)

여러 에이전트의 공유 브라우저 사용 순서를 조정하는 협력형 도구입니다.

## 왜 만들었나요

여러 에이전트가 한 데스크톱의 선택 탭·키보드·마우스·화면을 공유하면 서로 다른 작업의 클릭, 입력, 파일 선택창, 화면 관찰이 간섭할 수 있습니다. 탭을 나누는 것만으로 공유 포커스 문제가 사라지지는 않습니다. 이 도구는 참여 작업자에게 공통 점유 기록, 대기열, 안전한 양도와 중단 후 재개 절차를 제공합니다.

현재는 공유 UI를 하나의 자원으로 다루는 보수적인 정책입니다. 모든 브라우저 작업을 직렬화해야 한다거나 모든 탭별 DOM/API가 충돌한다고 주장하지 않습니다. 충돌을 완전히 막는 보장도 아닙니다. 독립적인 탭 작업의 병렬화는 검증할 향후 과제이며 이번 기능에 포함하지 않습니다.

## 포함된 기능

**0.3.5**는 Python 라이브러리와 CLI입니다. 로컬 SQLite DB 하나, 원자적 점유, 우선순위와 대기시간 반영, 고유 요청 ID, 세대별 토큰, begin/end, 탭 보존 기록, 검증 후 복구를 제공합니다. 외부 런타임 패키지는 필요 없습니다. 모든 도구 래퍼가 절차에 참여해야 하며 직접 호출까지 강제로 차단하지 않습니다.

브라우저 드라이버·로그인·서비스 계정·daemon·자동 작업자 메시지·실제 운영 상태는 포함하지 않습니다. 실험 중인 v0.4의 점유자 문의/keepalive는 **이번 배포에 포함하거나 활성화하지 않습니다**. 호스트의 작업 수명과 timeout 연동 검증이 남아 있습니다.

## 폴더 구성

- `src/agent_browser_coordinator/`: 설치되는 단일 구현과 CLI
- `tests/`: 기능·보안 회귀, `tests/reviews/`: 독립 검수 회귀
- `scripts/`: 검증·빌드·패키징·복원 도구
- `examples/`: 실제 UI를 호출하지 않는 사용 예제
- `docs/`: 한국어·영어·일본어 운영 문서와 검토 기록
- `config/`: 공개 파일 허용목록

개발·배포 명령은 저장소 루트에서 `python -m scripts.release_gate --output-dir dist/new-reviewed-release`처럼 실행합니다. 루트에 구현 사본을 두지 않습니다.

## 시작하기

- [설치](docs/ko/INSTALL.md)
- [에이전트 설치 프롬프트 예제](docs/ko/AGENT_INSTALL_PROMPTS.md)
- [공통 자원 설정](docs/ko/CONFIGURATION.md)
- [CLI와 Python 사용 예제](docs/ko/USAGE.md)
- [양도와 복구](docs/ko/RECOVERY.md)
- [한계와 향후 과제](docs/ko/LIMITATIONS.md)
- [개발·릴리스](CONTRIBUTING.md) · [변경 기록](CHANGELOG.md) · [보안 경계](SECURITY.md)

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
agent-browser-coordinator --version
python examples/two_workers.py
```

demo는 합성 작업자와 임시 상태만 사용하며 실제 브라우저를 열지 않습니다. 실제 도구를 연결하기 전 초기화·복구의 선행 조건을 읽으세요. 점유 성공은 외부 게시·전송 등 행동의 승인이 아닙니다.

[MIT 라이선스](LICENSE). [소스와 라이선스 설명](NOTICE.md)을 참고하세요.

[배포 전 보안 검토와 필수 검증 명령](docs/SECURITY_REVIEW.md)
