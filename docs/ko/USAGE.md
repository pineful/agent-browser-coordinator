# 모든 실제 호출 앞뒤에 점유 절차 적용

## 짧은 점유와 작업 분류

어댑터는 `agent_browser_coordinator.guard.run_guarded`를 사용해 begin의 성공·비재생 응답과 actor/token/action 일치를 확인한 뒤에만 콜백을 실행할 수 있습니다. 콜백은 `(terminated, value)`를 반환합니다. 예외나 종료 불명은 active action을 진단용으로 남깁니다. 참여 래퍼의 `YIELD_REQUIRED` 뒤 도구 호출을 막지만 래퍼 밖 직접 호출은 막지 못합니다. 새 화면 확인은 `kind='observation'`, 유용한 작업 호출은 `kind='work'`(기본값)로 표시합니다. 체크포인트로 재개한 owner는 최대 두 호출 안에서 관찰 뒤 작업 한 번을 마칠 기회를 얻습니다. 관찰 두 번으로 예산을 늘릴 수 없으며 lease 만료와 연속 상한은 그대로 적용됩니다.

UI 밖에서 준비 중이면 작업자는 `readiness --actor worker-a --request ready-001 --args '{"state":"preparing"}'`를 기록하고 준비가 끝나면 `state=ready`로 바꿀 수 있습니다. preparing 대기자는 선정에서 제외됩니다. `status.next_ready_actor`는 기존 FIFO·우선순위·aging에 따라 다음 ready 대기자를 보여주고 `status.handoff_ready`는 현재 owner가 안전 경계에서 체크포인트 후 양보해야 하는 신호입니다. 상태 신호이지 작업자 생성·실행 보장은 아닙니다. 이전 클라이언트의 acquire는 기본 ready입니다.

유한한 UI 호출 한 번에만 acquire → 현재 owner/token 확인 → begin → 도구 호출 → end를 적용하고 안전 경계에서 yield/release합니다. 문서 준비·파일 분석·서버 생성/검수/발행 간격 대기는 점유 밖에서 진행합니다. 재개 시 새 token으로 재획득하고 현재 화면을 다시 확인합니다. 대기자가 있으면 설정 가능한 점유 예산(기본 180초)을 다음 begin에서 검사합니다. 기존 queue aging 120초와 연속 상한 30분도 유지됩니다. 진행 중 호출은 중단·강탈하지 않으며 대기자가 취소되면 불필요한 교대를 피합니다.

`heartbeat`는 수동 작업자 생존 관측만 기록합니다. lease를 갱신하거나 도구의 진행 결과를 증명하지 않습니다. 실행환경 자동 heartbeat bridge는 없습니다. status의 `last_keep_alive_at`, `active`, owner deadline을 구분해 확인하세요.

`classify_work(kind, capability=...)`는 보수적인 계획 힌트입니다. unknown, 공유 화면/키보드, 네이티브 파일 선택창, 모달, 브라우저 UI는 순차 점유합니다. 파일 분석과 서버 생성 대기는 점유 밖에서 병렬 처리할 수 있습니다. `tab_id`만으로 병렬 안전을 주장하지 않습니다. 어댑터 식별자·증거 참조·검증된 capability와 세션/입력/포커스/대화상자 격리 확인이 모두 있어야 탭 API를 병렬 *후보*로 분류합니다. 이 라이브러리는 호스트 증거 검증이나 실제 병렬 브라우저 호출을 실행하지 않습니다.

CLI는 JSON을 반환하며 거절·잘못된 요청에는 종료 코드 2를 반환합니다. `ok`, `replay`, `owner.actor`, `owner.token`, `active`를 읽습니다. 대기 등록은 점유 획득이 아닙니다. 재생된 begin 성공 응답은 실제 도구를 다시 실행할 허가가 아닙니다.

아래를 한꺼번에 실행하지 마세요. acquire의 실제 owner가 worker-a일 때 받은 token으로 `CURRENT_TOKEN`을 바꿉니다. 새 명령의 request ID는 매번 바꾸고 begin의 새 성공·비재생 상태를 확인한 뒤 실제 승인된 도구를 한 번 실행합니다.

```sh
agent-browser-coordinator --db "$ABC_DB" acquire --actor worker-a   --request acquire-a-001 --args '{"priority":20,"lease":120}'
agent-browser-coordinator --db "$ABC_DB" begin --actor worker-a   --request begin-a-001 --args '{"token":"CURRENT_TOKEN","action":"action-a-001"}'
# ONE authorized bounded tool call, only after non-replay begin success.
agent-browser-coordinator --db "$ABC_DB" end --actor worker-a   --request end-a-001 --args '{"token":"CURRENT_TOKEN","action":"action-a-001"}'
```

end는 해당 호출이 확실히 종료됐을 때만 실행합니다. 확정된 실패도 종료 기록을 남길 수 있지만 시작·완료 불명이면 unresolved 상태를 보존해 운영자에게 조정을 요청합니다. 무조건 finally에서 end하여 불명 상태를 지우지 않습니다. 새 점유·재개마다 첫 읽기 호출에서 실제 화면·URL/계정·대상·저장 상태·이전 결과를 확인하며 옛 handle이나 좌표를 쓰지 않습니다.

Python도 같은 규약입니다.

```python
from agent_browser_coordinator import Coordinator
co = Coordinator("/absolute/path/to/existing-shared.db")
snapshot = co.status()  # read-only; missing DB is not created
```

완전한 합성 흐름은 `python examples/safe_mock_worker.py`, 두 작업자 양도는 `python examples/two_workers.py`로 실행합니다. 실제 브라우저는 호출하지 않습니다.

호출이 모두 끝난 안전 지점에서 체크포인트를 남기고 양도합니다.

```sh
agent-browser-coordinator --db "$ABC_DB" yield --actor worker-a   --request yield-a-001   --args '{"token":"CURRENT_TOKEN","safe":true,"checkpoint":"resume-a-001"}'
```

yield는 자신을 다시 대기열에 넣고 탭을 보존합니다. release는 재등록 없이 현재 점유를 끝냅니다. 대기 취소는 자신의 actor로 cancel합니다. 재개 시 새 token을 얻습니다. 만료 후 자발적 반환은 active가 없고 실제 미결 호출이 없을 때 `no_pending_ui=true`도 필요합니다. begin 거절을 우회해 저장 버튼을 누르지 않습니다.

tab 명령은 working/paused/held/complete와 unsaved의 논리 기록입니다. 자기 소유·완료·저장됨을 실제 확인한 탭만 close-begin → 실제 닫기 → close-end로 정리합니다. 기록은 탭 생존 보장이 아닙니다. 실제 전체 인벤토리를 확인해야 inventory complete=true로 설정할 수 있습니다. 브라우저 종료는 빈 owner/queue/tabs/active와 확인된 inventory를 전제로 shutdown prepare/start/end 게이트를 사용합니다.

`dashboard --output status.html`은 로컬 읽기 전용 스냅샷입니다. 서버·자동 갱신·heartbeat·자동 복구가 아닙니다.

[양도/복구](RECOVERY.md) · [한계](LIMITATIONS.md)
