# 안전한 양도와 검증 후 복구

## 정상 양도

실행 중인 정확한 호출을 끝내고 최소 체크포인트와 미저장 상태를 남긴 뒤 yield 또는 release합니다. 다음 소유자는 현재 화면·서비스 결과부터 확인합니다. 다른 작업자의 탭을 닫거나 불명확한 게시·업로드를 실패로 간주해 반복하지 않습니다.

파일 선택과 서버 처리는 별개입니다. native 선택창 소실이나 짧은 이벤트 timeout만으로 성공·실패를 단정하지 않습니다. 유한한 관찰 기한 안에서 실제 미리보기·처리 상태·적용/다음 활성·렌더링·저장·대화상자 닫힘을 확인합니다. 모든 작업에 고정 sleep을 강제하거나 결과 불명 상태에서 같은 파일을 다시 보내지 않습니다.

## 만료·중단 소유자

안정판 0.3.4은 만료만으로 점유를 자동 회수하지 않습니다. 운영자가 신규 제출을 중단시키고 freeze한 뒤 정확한 revision, owner token, shutdown token을 읽습니다.

```sh
agent-browser-coordinator --db "$ABC_DB" freeze --actor coordinator-operator   --request freeze-001
agent-browser-coordinator --db "$ABC_DB" status
```

옛 작업자가 더 제출하지 않는다는 확인과 이미 제출한 모든 실제 도구의 종료 확인을 별도로 얻습니다. 그 뒤 recover에 `verified_idle=true`, `old_worker_quiescent=true`, 불투명 evidence와 정확한 `expected_revision`, `expected_token`, `expected_shutdown_token`을 제공합니다. 없는 token은 null입니다. 미확인 사실을 true로 채우는 복사 명령을 제공하지 않습니다. 상태가 변해 거절되면 강제하지 말고 다시 확인합니다.

복구 뒤 새 generation을 사용하고 옛 token은 폐기합니다. 탭 기록을 남겨도 실제 탭 상태는 재검증해야 합니다. 이 절차는 원격 호출을 취소하거나 외부 상태를 증명하지 않습니다.

미결 불명에는 frozen 상태의 원래 owner/action과 운영자의 exact-revision permit이 필요한 diagnose-authorize → 원소유자의 diagnose-begin/end를 적용합니다. manual-reconcile은 원 결과 unknown과 별도 수동 확인 결과를 구분합니다. 브라우저 자체의 읽기 전용 권한은 아니므로 해당 검증 코드·합성 진단 시험을 먼저 읽습니다. timeout만으로 종료 근거를 만들지 않습니다.

## 소스·DB 분실

신뢰 가능한 릴리스를 새 빈 폴더로 복원합니다. `python verify_backup.py ARCHIVE --sha256 EXPECTED_SHA256 --destination NEW_DIRECTORY`는 신뢰할 수 있는 별도 해시, 정확한 허용목록, 각 파일 해시를 추출 전에 확인하고 합성 시험을 실행합니다. 기존 목적지는 거절합니다. DB를 포함하거나 활성화하지 않습니다.

기존 DB가 정상이면 그대로 사용합니다. 실행 중 DB/WAL/SHM을 복사·교체하지 않습니다. DB가 없거나 신뢰할 수 없을 때는 모든 작업자 중지·실제 미결 종료 후에만 새 DB/epoch를 명시 결정합니다. inventory는 미확인으로 시작하고 옛 허가를 폐기한 뒤 단일 게이트로 실제 화면·결과를 읽고 작업자가 새 점유를 얻도록 합니다. 코드 복원은 세션 복원이 아닙니다.

[한계](LIMITATIONS.md) · [사용 예제](USAGE.md)

checksum은 출처 인증이 아닙니다. 복원 검증은 압축 안의 코드를 실행하므로 신뢰한 릴리스만 사용하고, 새로 만든 비공개 임시 폴더 같은 신뢰할 수 있는 부모 아래의 새 경로를 지정합니다. symlink 부모와 기존 출력은 거절합니다.
