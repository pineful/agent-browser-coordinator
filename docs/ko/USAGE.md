# 모든 실제 호출 앞뒤에 점유 절차 적용

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

완전한 합성 흐름은 `python examples/safe_mock_worker.py`, 두 작업자 양도는 `python demo.py`로 실행합니다. 실제 브라우저는 호출하지 않습니다.

호출이 모두 끝난 안전 지점에서 체크포인트를 남기고 양도합니다.

```sh
agent-browser-coordinator --db "$ABC_DB" yield --actor worker-a   --request yield-a-001   --args '{"token":"CURRENT_TOKEN","safe":true,"checkpoint":"resume-a-001"}'
```

yield는 자신을 다시 대기열에 넣고 탭을 보존합니다. release는 재등록 없이 현재 점유를 끝냅니다. 대기 취소는 자신의 actor로 cancel합니다. 재개 시 새 token을 얻습니다. 만료 후 자발적 반환은 active가 없고 실제 미결 호출이 없을 때 `no_pending_ui=true`도 필요합니다. begin 거절을 우회해 저장 버튼을 누르지 않습니다.

tab 명령은 working/paused/held/complete와 unsaved의 논리 기록입니다. 자기 소유·완료·저장됨을 실제 확인한 탭만 close-begin → 실제 닫기 → close-end로 정리합니다. 기록은 탭 생존 보장이 아닙니다. 실제 전체 인벤토리를 확인해야 inventory complete=true로 설정할 수 있습니다. 브라우저 종료는 빈 owner/queue/tabs/active와 확인된 inventory를 전제로 shutdown prepare/start/end 게이트를 사용합니다.

`dashboard --output status.html`은 로컬 읽기 전용 스냅샷입니다. 서버·자동 갱신·heartbeat·자동 복구가 아닙니다.

[양도/복구](RECOVERY.md) · [한계](LIMITATIONS.md)
